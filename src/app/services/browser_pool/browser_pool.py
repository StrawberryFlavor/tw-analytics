"""
浏览器池管理
提供浏览器实例的池化管理、并发控制和健康监控
"""

import asyncio
import logging
import os
import time
import uuid
from typing import List, Dict, Any, Tuple
from playwright.async_api import async_playwright, BrowserContext, Page

from .browser_instance import PooledBrowserInstance, InstanceStatus


class BrowserPool:
    """
    浏览器池管理器
    
    管理多个浏览器实例，提供高效的资源复用和并发处理能力
    """
    
    def __init__(self, 
                 min_size: int = None,
                 max_size: int = None, 
                 max_idle_time: float = None,
                 health_check_interval: float = None):
        """
        初始化浏览器池
        
        Args:
            min_size: 最小池大小（默认从配置读取）
            max_size: 最大池大小（默认从配置读取）
            max_idle_time: 最大空闲时间（秒，默认从配置读取）
            health_check_interval: 健康检查间隔（秒，默认从配置读取）
        """
        from ...config import Config
        
        self.min_size = min_size or Config.BROWSER_POOL_MIN_SIZE
        self.max_size = max_size or Config.BROWSER_POOL_MAX_SIZE
        self.max_idle_time = max_idle_time or Config.get_max_idle_time()
        self.health_check_interval = health_check_interval or Config.get_health_check_interval()
        
        self.instances: List[PooledBrowserInstance] = []
        self.playwright = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._disposing = False
        
        # 统计管理器
        from .pool_metrics import PoolMetricsManager
        self._metrics_manager = PoolMetricsManager()
        
        # 实例选择器
        from .instance_selector import InstanceSelector
        # 使用最少使用策略，避免某些实例过度使用
        from .instance_selector import SelectionStrategy
        self._instance_selector = InstanceSelector(SelectionStrategy.LEAST_USED)
        
        # 实例预热器
        from .instance_warmer import InstanceWarmer
        self._instance_warmer = InstanceWarmer()
        
        # 健康检查管理器
        from .pool_health_manager import PoolHealthManager
        self._health_manager = PoolHealthManager(
            health_check_interval=self.health_check_interval,
            min_pool_size=self.min_size,
            instance_creator=self._create_browser_instance,
            instance_disposer=None  # 使用默认的实例dispose方法
        )
        
        # 清理管理器
        from .pool_cleanup_manager import PoolCleanupManager
        self._cleanup_manager = PoolCleanupManager(
            max_idle_time=self.max_idle_time,
            min_pool_size=self.min_size,
            instance_disposer=None  # 使用默认的实例dispose方法
        )
        
        # 账户管理器
        self._account_manager = None
        
        # 初始化 logger (必须在其他组件之前)
        self.logger = logging.getLogger(__name__)
        
        # 实例轮换管理器 (使用智能配置)
        if Config.BROWSER_POOL_ROTATION_ENABLED:
            from .instance_rotation import InstanceRotationManager, InstanceRotationConfig
            rotation_config = InstanceRotationConfig.from_app_config()
            self._rotation_manager = InstanceRotationManager(rotation_config)
            self.logger.info(f"启用实例轮换 - 生命周期: {rotation_config.max_instance_lifetime}s, 使用次数: {rotation_config.max_usage_count}, 概率: {rotation_config.rotation_probability}")
        else:
            self._rotation_manager = None
            self.logger.info("实例轮换已禁用")
        
        
        # 恢复管理器
        self._recovery_manager = None
    
    async def initialize(self) -> None:
        """初始化浏览器池"""
        async with self._lock:
            if self._initialized:
                return
            
            try:
                self.logger.info(f"初始化浏览器池，最小大小: {self.min_size}, 最大大小: {self.max_size}")
                
                # 启动 Playwright
                self.playwright = await async_playwright().start()
                
                # 初始化恢复管理器
                from .recovery_manager import RecoveryManager
                self._recovery_manager = RecoveryManager(self)
                
                # 预创建最小数量的浏览器实例
                for i in range(self.min_size):
                    instance = await self._create_browser_instance()
                    self.instances.append(instance)
                    self.logger.info(f"预创建浏览器实例 {i+1}/{self.min_size}: {instance.instance_id}")
                
                self._initialized = True
                
                # 启动后台任务
                self._health_manager.set_health_check_callback(self._perform_health_check)
                self._health_manager.start_health_monitoring()
                
                self._cleanup_manager.set_cleanup_callback(self._perform_cleanup)
                self._cleanup_manager.start_cleanup_monitoring()
                
                self.logger.info(f"浏览器池初始化完成，当前实例数: {len(self.instances)}")
                
            except Exception as e:
                self.logger.error(f"浏览器池初始化失败: {e}")
                await self._cleanup_all()
                raise
    
    def set_account_manager(self, account_manager):
        """
        设置账户管理器
        
        Args:
            account_manager: 账户管理器实例
        """
        self._account_manager = account_manager
        
        # 为所有现有实例设置账户管理器
        for instance in self.instances:
            instance.set_account_manager(account_manager)
        
        self.logger.info("已为浏览器池设置账户管理器")
    
    async def initialize_with_account_manager(self, account_manager=None):
        """
        初始化浏览器池并设置账户管理器
        
        Args:
            account_manager: 账户管理器实例，如果为None则创建默认实例
        """
        # 先初始化浏览器池
        await self.initialize()
        
        # 设置账户管理器
        if account_manager is None:
            from src.account_management import AccountManager
            account_manager = AccountManager()
        
        self.set_account_manager(account_manager)
        
        self.logger.info("浏览器池和账户管理器初始化完成")
    
    async def _create_browser_instance(self) -> PooledBrowserInstance:
        """创建新的浏览器实例"""
        instance_id = f"browser-{uuid.uuid4().hex[:8]}"
        
        try:
            # 使用智能代理管理器获取代理配置
            proxy_config, is_smart_managed = await self._get_smart_proxy_config()
            
            # 如果智能代理管理器没有返回配置，并且不是智能管理的，才回退到传统PLAYWRIGHT_PROXY
            if not proxy_config and not is_smart_managed:
                proxy = os.getenv('PLAYWRIGHT_PROXY')
                if proxy:
                    if not proxy.startswith(('http://', 'https://', 'socks5://')):
                        proxy = f"http://{proxy}"
                    proxy_config = {"server": proxy}
                    self.logger.debug(f"使用传统代理配置: {proxy}")
                else:
                    self.logger.debug("未配置任何代理，使用直连")
            elif not proxy_config and is_smart_managed:
                self.logger.debug("智能代理管理器选择直连，忽略传统代理配置")
            
            headless = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
            
            # 创建浏览器（添加超时保护）
            self.logger.info(f"开始创建浏览器实例: {instance_id}")
            browser = await asyncio.wait_for(
                self.playwright.chromium.launch(
                    headless=headless,
                    proxy=proxy_config,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                ),
                timeout=30.0  # 30秒超时
            )
            self.logger.info(f"浏览器实例创建成功: {instance_id}")
            
            instance = PooledBrowserInstance(browser, instance_id)
            
            # 如果已设置账户管理器，为新实例设置
            if self._account_manager:
                instance.set_account_manager(self._account_manager)
            
            # 预热实例（可选，添加超时保护）
            await self._instance_warmer.warmup_instance(instance, timeout=15.0)
            
            return instance
            
        except Exception as e:
            self.logger.error(f"创建浏览器实例 {instance_id} 失败: {e}")
            raise
    
    async def _rotate_instance_async(self, instance_id: str):
        """异步轮换实例"""
        try:
            async with self._lock:
                # 找到要轮换的实例
                instance_to_rotate = None
                for instance in self.instances:
                    if instance.instance_id == instance_id:
                        instance_to_rotate = instance
                        break
                
                if not instance_to_rotate:
                    self.logger.warning(f"未找到要轮换的实例: {instance_id}")
                    return
                
                # 创建新实例替换
                self.logger.info(f"开始轮换实例: {instance_id}")
                new_instance = None
                try:
                    # 步骤1：创建新实例
                    new_instance = await self._create_browser_instance()
                    
                    # 步骤2：替换实例
                    old_index = self.instances.index(instance_to_rotate)
                    self.instances[old_index] = new_instance
                    
                    # 步骤3：注册新实例到轮换管理器
                    if self._rotation_manager:
                        self._rotation_manager.register_instance(new_instance.instance_id)
                        # 清理旧实例跟踪
                        self._rotation_manager.cleanup_instance_tracking(instance_id)
                    
                    self.logger.info(f"实例轮换完成: {instance_id} -> {new_instance.instance_id}")
                    
                except Exception as e:
                    self.logger.error(f"实例轮换失败: {instance_id}, 错误: {e}")
                    # 如果创建新实例失败，标记旧实例为ERROR状态，避免继续使用
                    if instance_to_rotate:
                        instance_to_rotate.status = InstanceStatus.ERROR
                        instance_to_rotate.error_count += 10  # 大幅增加错误计数
                        self.logger.warning(f"实例 {instance_id} 轮换失败，标记为ERROR状态")
                    
                    if new_instance:
                        try:
                            # 尝试关闭新创建的失败实例
                            await new_instance.dispose()
                        except Exception as dispose_error:
                            self.logger.error(f"清理失败的新实例时出错: {dispose_error}")
                    return
                
                # 步骤4：关闭旧实例（无论是否有异常都要执行）
                try:
                    await instance_to_rotate.dispose()
                    self.logger.info(f"旧实例 {instance_id} 已成功关闭")
                except Exception as dispose_error:
                    self.logger.error(f"关闭旧实例 {instance_id} 失败: {dispose_error}")
                    # 即使关闭失败，也不影响新实例的使用
                    
        except Exception as e:
            self.logger.error(f"异步轮换过程失败: {e}")
    
    
    async def acquire_instance(self, timeout: float = 30.0) -> Tuple[PooledBrowserInstance, BrowserContext, Page]:
        """
        获取可用的浏览器实例
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            (instance, context, page) 元组
            
        Raises:
            asyncio.TimeoutError: 超时
            RuntimeError: 池已关闭或无法获取实例
        """
        if not self._initialized:
            await self.initialize()
        
        if self._disposing:
            raise RuntimeError("浏览器池正在关闭")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 分离池锁和实例锁，避免嵌套锁死锁
            available_instance = None
            should_create_new = False
            
            # 第一步：在池锁保护下寻找可用实例或决定是否创建新实例
            async with self._lock:
                self.logger.debug(f"寻找可用实例，当前池大小: {len(self.instances)}")
                
                # 调试：记录所有实例状态
                for i, inst in enumerate(self.instances):
                    self.logger.debug(f"实例 {i}: {inst.instance_id}, 状态: {inst.status.value}, "
                                    f"错误数: {inst.error_count}, 使用次数: {inst.usage_count}")
                
                # 使用选择器查找可用实例
                available_instance = self._instance_selector.find_available_instance(self.instances)
                
                # 如果没有空闲实例且未达到最大大小，标记需要创建新实例
                if available_instance is None and len(self.instances) < self.max_size:
                    should_create_new = True
                    self.logger.info(f"没有可用实例，将创建新实例 (当前: {len(self.instances)}, 最大: {self.max_size})")
                elif available_instance is None:
                    self.logger.warning(f"没有可用实例且已达到最大池大小 ({len(self.instances)}/{self.max_size})，"
                                      f"所有实例状态: {[(inst.instance_id, inst.status.value, inst.usage_count) for inst in self.instances]}")
                    
                    # 检查是否有长时间占用的实例，强制释放
                    current_time = time.time()
                    for inst in self.instances:
                        if (inst.status == InstanceStatus.BUSY and 
                            hasattr(inst, 'acquire_time') and 
                            inst.acquire_time and
                            current_time - inst.acquire_time > 300):  # 5分钟
                            self.logger.warning(f"强制释放长时间占用的实例: {inst.instance_id}")
                            try:
                                await inst.release(cleanup=False)
                            except Exception as e:
                                self.logger.error(f"强制释放实例失败: {e}")
                    
                    # 检查是否所有实例都因为使用次数过多而不可用
                    all_idle = all(inst.status == InstanceStatus.IDLE for inst in self.instances)
                    
                    if all_idle and self.instances:
                        # 找出使用次数最多的实例进行替换
                        oldest_instance = max(self.instances, key=lambda x: x.usage_count)
                        self.logger.warning(f"所有实例都已达到使用次数限制，替换使用最多的实例: {oldest_instance.instance_id} (使用次数: {oldest_instance.usage_count})")
                        
                        # 移除旧实例
                        self.instances.remove(oldest_instance)
                        
                        # 销毁旧实例
                        try:
                            await oldest_instance.dispose()
                        except Exception as e:
                            self.logger.error(f"销毁旧实例失败: {e}")
                        
                        # 创建新实例标记
                        should_create_new = True
                        self.logger.info("将创建新实例替换旧实例")
            
            # 第二步：在池锁外获取实例，避免嵌套锁
            if available_instance:
                self.logger.debug(f"尝试获取可用实例: {available_instance.instance_id}")
                try:
                    context, page = await available_instance.acquire()
                    self._metrics_manager.record_request_start()
                    self._metrics_manager.record_pool_hit()
                    
                    # 记录实例使用并检查是否需要轮换
                    if self._rotation_manager:
                        self._rotation_manager.record_usage(available_instance.instance_id)
                        should_rotate, reason = self._rotation_manager.should_rotate_instance(available_instance.instance_id)
                        
                        # 强制检查：如果使用次数超过硬限制，立即轮换
                        if available_instance.usage_count > 30:
                            self.logger.warning(f"实例 {available_instance.instance_id} 使用次数过多 ({available_instance.usage_count})，强制轮换")
                            should_rotate = True
                            reason = RotationReason.USAGE_LIMIT
                        
                        if should_rotate:
                            self.logger.info(f"实例 {available_instance.instance_id} 需要轮换 (原因: {reason.value if reason else 'unknown'})")
                            # 异步轮换，不阻塞当前请求
                            asyncio.create_task(self._rotate_instance_async(available_instance.instance_id))
                    
                    stats_summary = self._metrics_manager.get_summary_text()
                    self.logger.info(f"成功从池中获取实例: {available_instance.instance_id} ({stats_summary})")
                    
                    # 打印负载分布统计
                    instance_usage = {inst.instance_id: inst.usage_count for inst in self.instances}
                    self.logger.info(f"负载分布: {instance_usage}")
                    
                    return available_instance, context, page
                except Exception as e:
                    self.logger.warning(f"获取实例 {available_instance.instance_id} 失败: {e}")
                    # 使用恢复管理器处理故障
                    if self._recovery_manager:
                        await self._recovery_manager.handle_failure(available_instance, e)
                    continue
            
            # 第三步：如果需要创建新实例
            elif should_create_new:
                self.logger.debug("开始创建新实例")
                try:
                    new_instance = await self._create_browser_instance()
                    
                    # 在池锁保护下添加到池中
                    async with self._lock:
                        self.instances.append(new_instance)
                    
                    context, page = await new_instance.acquire()
                    self._metrics_manager.record_request_start()
                    self._metrics_manager.record_pool_miss()
                    self.logger.info(f"创建新实例: {new_instance.instance_id}, 当前池大小: {len(self.instances)}")
                    return new_instance, context, page
                except Exception as e:
                    self.logger.error(f"创建新实例失败: {e}")
            else:
                self.logger.debug("没有可用实例且无法创建新实例，等待重试")
            
            # 等待一小段时间后重试，每隔5秒进行一次强制检查
            elapsed = time.time() - start_time
            if elapsed % 5 < 0.1:  # 每5秒执行一次
                await self._force_check_stuck_instances()
            await asyncio.sleep(0.1)
        
        raise asyncio.TimeoutError(f"获取浏览器实例超时 ({timeout}秒)")
    
    async def _force_check_stuck_instances(self):
        """强制检查并恢复卡住的实例"""
        current_time = time.time()
        stuck_instances = []
        
        async with self._lock:
            for inst in self.instances:
                # 检查长时间占用的实例（超过2分钟）
                if (inst.status == InstanceStatus.BUSY and 
                    inst.acquire_time and 
                    current_time - inst.acquire_time > 120):  # 2分钟
                    stuck_instances.append(inst)
        
        # 在锁外处理卡住的实例
        for inst in stuck_instances:
            self.logger.warning(f"检测到卡住的实例 {inst.instance_id}，尝试强制恢复")
            try:
                await inst.release(cleanup=True)
                self.logger.info(f"成功恢复实例: {inst.instance_id}")
            except Exception as e:
                self.logger.error(f"恢复实例失败 {inst.instance_id}: {e}")
                # 标记为错误状态
                inst.status = InstanceStatus.ERROR
    
    async def release_instance(self, instance: PooledBrowserInstance, success: bool = True):
        """
        释放浏览器实例
        
        Args:
            instance: 要释放的实例
            success: 操作是否成功
        """
        try:
            self.logger.info(f"释放实例: {instance.instance_id} (成功: {success})")
            
            # 增加账户使用计数并检查账户切换（在清理上下文之前）
            if success and hasattr(instance, 'increment_account_usage'):
                instance.increment_account_usage()
                
                # 检查是否需要切换账户（必须在release之前执行）
                if hasattr(instance, 'should_switch_account') and instance.should_switch_account():
                    self.logger.info(f"实例 {instance.instance_id} 达到切换阈值，尝试切换账户")
                    try:
                        switch_success = await instance.check_and_switch_account()
                        if switch_success:
                            self.logger.info(f"实例 {instance.instance_id} 账户切换成功")
                        else:
                            self.logger.warning(f"实例 {instance.instance_id} 账户切换失败")
                    except Exception as switch_error:
                        self.logger.error(f"实例 {instance.instance_id} 账户切换异常: {switch_error}")
            
            # 释放实例（失败时清理上下文，成功时保留状态）
            cleanup_needed = not success or instance.error_count > 2
            await instance.release(cleanup=cleanup_needed)
            
            if success:
                self._metrics_manager.record_request_success()
            else:
                self._metrics_manager.record_request_failure()
                # 如果请求失败，标记实例为有问题状态
                instance.error_count += 1
                if instance.error_count > 3:  # 连续失败3次以上
                    instance.status = InstanceStatus.ERROR
                    self.logger.warning(f"实例 {instance.instance_id} 失败次数过多，标记为ERROR状态")
                
            self.logger.debug(f"释放实例: {instance.instance_id}")
            
        except Exception as e:
            self.logger.error(f"释放实例 {instance.instance_id} 失败: {e}")
    
    async def _perform_health_check(self):
        """执行健康检查 - 由健康管理器定期调用"""
        async with self._lock:
            await self._health_manager.perform_health_check(self.instances)
    
    async def _perform_cleanup(self):
        """执行清理 - 由清理管理器定期调用"""
        async with self._lock:
            await self._cleanup_manager.cleanup_idle_instances(self.instances)
    
    
    async def get_pool_status(self) -> Dict[str, Any]:
        """获取池状态"""
        async with self._lock:
            status = {
                'initialized': self._initialized,
                'disposing': self._disposing,
                'pool_config': {
                    'min_size': self.min_size,
                    'max_size': self.max_size,
                    'max_idle_time': self.max_idle_time,
                    'health_check_interval': self.health_check_interval
                },
                'pool_stats': {
                    'total_instances': len(self.instances),
                    'idle_instances': sum(1 for i in self.instances if i.status == InstanceStatus.IDLE),
                    'busy_instances': sum(1 for i in self.instances if i.status == InstanceStatus.BUSY),
                    'error_instances': sum(1 for i in self.instances if i.status == InstanceStatus.ERROR),
                },
                'request_stats': self._metrics_manager.get_statistics(),
                'instances': [instance.get_metrics() for instance in self.instances]
            }
            
            # 添加恢复管理器指标
            if self._recovery_manager:
                status['recovery_metrics'] = self._recovery_manager.get_recovery_metrics()
            
            # 添加账户管理状态
            if self._account_manager:
                account_stats = self._account_manager.get_statistics()
                status['account_management'] = {
                    'enabled': True,
                    'total_accounts': account_stats.get('total_accounts', 0),
                    'active_accounts': account_stats.get('status_distribution', {}).get('active', 0),
                    'account_stats': account_stats
                }
                
                # 添加每个实例的账户状态
                instance_accounts = []
                for instance in self.instances:
                    if hasattr(instance, 'get_account_status'):
                        instance_accounts.append(instance.get_account_status())
                
                status['account_management']['instance_accounts'] = instance_accounts
            else:
                status['account_management'] = {'enabled': False}
            
            return status
    
    async def dispose(self):
        """关闭浏览器池"""
        if self._disposing:
            self.logger.debug("浏览器池正在清理中，跳过重复清理")
            return
            
        self.logger.info("开始关闭浏览器池")
        self._disposing = True
        
        try:
            # 取消后台任务
            self.logger.debug("停止健康监控...")
            self._health_manager.stop_health_monitoring()
            
            self.logger.debug("停止清理监控...")
            self._cleanup_manager.stop_cleanup_monitoring()
            
            # 等待任务结束（设置超时以防卡死）
            try:
                self.logger.debug("等待健康监控停止...")
                await asyncio.wait_for(
                    self._health_manager.wait_for_health_monitoring_stop(), 
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self.logger.warning("健康监控停止超时")
            
            try:
                self.logger.debug("等待清理监控停止...")
                await asyncio.wait_for(
                    self._cleanup_manager.wait_for_cleanup_stop(), 
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self.logger.warning("清理监控停止超时")
            
            # 清理所有实例
            self.logger.debug("清理所有实例...")
            await self._cleanup_all()
            
            self.logger.info("浏览器池已完全关闭")
            
        except Exception as e:
            self.logger.error(f"浏览器池关闭时出错: {e}")
            # 即使出错也要尝试强制清理
            try:
                await self._cleanup_all()
            except:
                pass
        finally:
            self._disposing = False
    
    async def _cleanup_all(self):
        """清理所有资源"""
        # 关闭所有实例（带超时保护）
        if self.instances:
            self.logger.debug(f"清理 {len(self.instances)} 个浏览器实例...")
            cleanup_tasks = [instance.dispose() for instance in self.instances]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*cleanup_tasks, return_exceptions=True),
                    timeout=30.0  # 30秒超时
                )
            except asyncio.TimeoutError:
                self.logger.warning("浏览器实例清理超时，强制清理...")
            finally:
                self.instances.clear()
        
        # 关闭 Playwright（带超时保护）
        if self.playwright:
            try:
                self.logger.debug("关闭Playwright...")
                await asyncio.wait_for(self.playwright.stop(), timeout=10.0)
                self.logger.debug("Playwright已关闭")
            except asyncio.TimeoutError:
                self.logger.warning("Playwright关闭超时")
            except Exception as e:
                self.logger.error(f"关闭Playwright失败: {e}")
            finally:
                self.playwright = None
        
        self._initialized = False
        self.logger.debug("所有资源清理完成")
    
    async def _get_smart_proxy_config(self):
        """使用智能代理管理器获取代理配置
        
        Returns:
            tuple: (proxy_config, is_smart_managed)
                - proxy_config: 代理配置字典或None
                - is_smart_managed: 是否由智能代理管理器管理
        """
        try:
            # 导入智能代理管理器
            from ..view_booster.smart_proxy_manager import get_smart_proxy_manager
            
            manager = get_smart_proxy_manager()
            proxy_config = await manager.get_proxy_config()
            
            if proxy_config:
                # 将httpx格式的代理配置转换为Playwright格式
                proxy_url = proxy_config.get('http://') or proxy_config.get('https://')
                if proxy_url:
                    self.logger.info(f"智能代理管理器选择代理: {proxy_url[:50]}...")
                    return {"server": proxy_url}, True
            
            self.logger.debug("智能代理管理器选择直连模式")
            return None, True  # 智能管理器选择直连
            
        except Exception as e:
            self.logger.warning(f"智能代理管理器获取配置失败: {e}")
            return None, False  # 智能管理器不可用，回退到传统模式
