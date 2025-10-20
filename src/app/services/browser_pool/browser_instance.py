"""
浏览器实例包装类
管理单个浏览器实例的生命周期和状态
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime
from playwright.async_api import Browser, BrowserContext, Page


class InstanceStatus(Enum):
    """浏览器实例状态"""
    IDLE = "idle"              # 空闲
    BUSY = "busy"              # 使用中  
    INITIALIZING = "initializing"  # 初始化中
    ERROR = "error"            # 错误状态
    DISPOSED = "disposed"      # 已销毁


class PooledBrowserInstance:
    """
    池化浏览器实例
    
    包装单个浏览器实例，提供状态管理、健康检查和资源清理
    """
    
    def __init__(self, browser: Browser, instance_id: str):
        self.browser = browser
        self.instance_id = instance_id
        self.status = InstanceStatus.IDLE
        self.created_at = time.time()
        self.last_used_at = time.time()
        self.acquire_time = None  # 实例被获取的时间，用于超时检测
        self.usage_count = 0
        self.error_count = 0
        self.current_context: Optional[BrowserContext] = None
        self.current_page: Optional[Page] = None
        
        # 账户管理相关
        self.account_usage_count = 0  # 当前账户使用次数
        self.account_switch_threshold = self._get_account_switch_threshold()  # 从配置获取切换阈值
        self.current_account = None  # 当前使用的账户
        self.using_env_cookie = True  # 是否使用环境变量cookie
        self.account_manager = None  # 账户管理器引用
        
        self.logger = logging.getLogger(f"{__name__}.{instance_id}")
        self._lock = asyncio.Lock()
        
        # 如果启用账户管理，初始化账户轮换
        self._init_account_rotation()
        
        self.logger.info(f"浏览器实例 {instance_id} 创建完成")
    
    def _init_account_rotation(self):
        """初始化账户轮换"""
        try:
            from ...config import Config
            if not Config.ACCOUNT_MANAGEMENT_ENABLED:
                return
                
            from src.account_management import AccountManager
            account_manager = AccountManager()
            
            # 使用轮换策略获取第一个账户
            account = account_manager.get_next_account(strategy="round_robin")
            if account:
                self.current_account = account
                self.logger.info(f"实例 {self.instance_id} 初始化账户轮换，当前账户: {account.username}")
            else:
                self.logger.warning(f"实例 {self.instance_id} 没有可用账户")
                
        except Exception as e:
            self.logger.debug(f"初始化账户轮换失败: {e}")
    
    def _get_account_switch_threshold(self) -> int:
        """从配置获取账户切换阈值"""
        try:
            from ...config import Config
            return Config.get_account_switch_threshold()
        except ImportError:
            # 如果无法导入配置，使用默认值
            return 100
    
    def _get_account_login_verification(self) -> bool:
        """从配置获取登录验证设置"""
        try:
            from ...config import Config
            return Config.ACCOUNT_LOGIN_VERIFICATION
        except ImportError:
            # 如果无法导入配置，使用默认值
            return False
    
    def _get_account_switch_strategy(self) -> str:
        """从配置获取账户切换策略"""
        try:
            from ...config import Config
            return Config.ACCOUNT_SWITCH_STRATEGY
        except ImportError:
            # 如果无法导入配置，使用默认值
            return 'cycle'
    
    async def acquire(self) -> tuple[BrowserContext, Page]:
        """
        获取浏览器上下文和页面
        
        Returns:
            (context, page) 元组
            
        Raises:
            RuntimeError: 如果实例不可用
        """
        async with self._lock:
            if self.status != InstanceStatus.IDLE:
                raise RuntimeError(f"实例 {self.instance_id} 状态为 {self.status.value}，无法获取")
            
            try:
                # 连接健康检测
                if not await self._check_connection_health():
                    self.logger.warning(f"实例 {self.instance_id} 连接不健康，强制重启")
                    await self._force_restart()
                
                self.status = InstanceStatus.BUSY
                self.last_used_at = time.time()
                self.acquire_time = time.time()  # 记录获取时间用于超时检测
                self.usage_count += 1
                
                # 如果没有现有的上下文和页面，创建新的
                if not self.current_context or not self.current_page:
                    await self._create_new_context()
                else:
                    # 复用现有页面（确保页面仍然有效）
                    try:
                        # 简单的健康检查
                        await self.current_page.evaluate("() => true")
                    except:
                        # 如果页面无效，重新创建
                        await self._cleanup_current_context()
                        await self._create_new_context()
                
                self.logger.debug(f"实例 {self.instance_id} 已获取，使用次数: {self.usage_count}")
                return self.current_context, self.current_page
                
            except Exception as e:
                self.status = InstanceStatus.ERROR
                self.error_count += 1
                self.logger.error(f"获取实例 {self.instance_id} 失败: {e}")
                raise
    
    async def release(self, cleanup: bool = True):
        """
        释放浏览器实例
        
        Args:
            cleanup: 是否清理当前上下文
        """
        async with self._lock:
            try:
                if cleanup and self.current_context:
                    await self._cleanup_current_context()
                
                self.status = InstanceStatus.IDLE
                self.last_used_at = time.time()
                self.acquire_time = None  # 清理获取时间
                
                self.logger.debug(f"实例 {self.instance_id} 已释放")
                
            except Exception as e:
                self.status = InstanceStatus.ERROR
                self.error_count += 1
                self.logger.error(f"释放实例 {self.instance_id} 失败: {e}")
    
    async def _create_new_context(self):
        """创建新的浏览器上下文和页面"""
        try:
            # 使用反检测管理器获取随机配置
            from .anti_detection import AntiDetectionManager
            anti_detection = AntiDetectionManager()
            config = anti_detection.get_random_config()
            
            # 创建上下文
            self.current_context = await self.browser.new_context(
                viewport=config['viewport'],
                user_agent=config['user_agent'],
                locale=config['language'],
                timezone_id=config['timezone'],
                extra_http_headers={
                    'Accept-Language': f"{config['language']},{config['language'][:2]};q=0.9",
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            )
            
            # 创建页面
            self.current_page = await self.current_context.new_page()
            
            # 添加反检测脚本
            stealth_script = anti_detection.get_basic_stealth_script()
            await self.current_page.add_init_script(stealth_script)
            
            # 如果有当前账户，设置认证cookies
            if self.current_account:
                await self._set_account_auth(self.current_context, self.current_account)
            
            self.logger.info(f"🎭 浏览器上下文创建成功")
            self.logger.debug(f"   UA: {config['user_agent'][:60]}...")
            self.logger.debug(f"   视口: {config['viewport']}")
            self.logger.debug(f"   语言: {config['language']}, 时区: {config['timezone']}")
            
            # 如果有账户，记录账户信息
            if self.current_account:
                self.logger.info(f"🔐 已设置账户认证: {self.current_account.username}")
            
        except Exception as e:
            self.logger.error(f"创建上下文失败: {e}")
            raise
    
    async def _cleanup_current_context(self):
        """清理当前上下文"""
        cleanup_errors = []
        
        # 清理页面
        if self.current_page:
            try:
                await self.current_page.close()
                self.logger.debug(f"实例 {self.instance_id} 页面已关闭")
            except Exception as e:
                cleanup_errors.append(f"关闭页面失败: {e}")
                self.logger.warning(f"实例 {self.instance_id} 关闭页面失败: {e}")
            finally:
                # 无论是否成功，都清除引用
                self.current_page = None
        
        # 清理上下文（即使页面关闭失败也要尝试）
        if self.current_context:
            try:
                await self.current_context.close()
                self.logger.debug(f"实例 {self.instance_id} 上下文已关闭")
            except Exception as e:
                cleanup_errors.append(f"关闭上下文失败: {e}")
                self.logger.warning(f"实例 {self.instance_id} 关闭上下文失败: {e}")
            finally:
                # 无论是否成功，都清除引用
                self.current_context = None
        
        # 如果有错误，记录但不抛出（让调用者决定是否需要处理）
        if cleanup_errors:
            self.logger.warning(f"实例 {self.instance_id} 清理上下文时发生错误: {'; '.join(cleanup_errors)}")
    
    async def _set_account_auth(self, context, account):
        """为浏览器上下文设置账户认证"""
        try:
            # 设置auth_token cookie
            cookies_to_set = [
                {
                    'name': 'auth_token',
                    'value': account.auth_token,
                    'domain': '.twitter.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': True,
                    'sameSite': 'None'
                },
                {
                    'name': 'auth_token',
                    'value': account.auth_token,
                    'domain': '.x.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': True,
                    'sameSite': 'None'
                }
            ]
            
            await context.add_cookies(cookies_to_set)
            self.logger.debug(f"已设置账户 {account.username} 的认证信息")
            
        except Exception as e:
            self.logger.error(f"设置账户认证失败: {e}")
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            True 如果实例健康
        """
        try:
            if self.status == InstanceStatus.DISPOSED:
                return False
            
            if not self.browser or not self.browser.is_connected():
                self.status = InstanceStatus.ERROR
                return False
            
            # 如果正在使用中，跳过详细检查
            if self.status == InstanceStatus.BUSY:
                return True
            
            # 检查是否可以创建上下文
            test_context = await self.browser.new_context()
            await test_context.close()
            
            return True
            
        except Exception as e:
            self.logger.warning(f"健康检查失败: {e}")
            self.status = InstanceStatus.ERROR
            return False
    
    async def dispose(self):
        """销毁浏览器实例"""
        async with self._lock:
            self.status = InstanceStatus.DISPOSED
            dispose_errors = []
            
            # 步骤1：清理当前上下文
            try:
                await self._cleanup_current_context()
            except Exception as e:
                dispose_errors.append(f"清理上下文失败: {e}")
                self.logger.error(f"实例 {self.instance_id} 清理上下文失败: {e}")
            
            # 步骤2：关闭浏览器（无论上下文清理是否成功都要执行）
            if self.browser:
                try:
                    await self.browser.close()
                    self.logger.info(f"实例 {self.instance_id} 浏览器已关闭")
                except Exception as e:
                    dispose_errors.append(f"关闭浏览器失败: {e}")
                    self.logger.error(f"实例 {self.instance_id} 关闭浏览器失败: {e}")
                finally:
                    # 确保引用被清除
                    self.browser = None
            
            # 记录错误但不抛出异常（避免导致数据源被标记为不可用）
            if dispose_errors:
                error_msg = f"销毁实例 {self.instance_id} 时发生错误: {'; '.join(dispose_errors)}"
                self.logger.warning(error_msg)
                # 不抛出异常，因为核心资源（浏览器引用）已经清理
            else:
                self.logger.info(f"实例 {self.instance_id} 已完全销毁")
    
    def is_available(self) -> bool:
        """检查实例是否可用"""
        # 基本状态检查
        if self.status != InstanceStatus.IDLE:
            self.logger.debug(f"实例 {self.instance_id} 不可用: 状态为 {self.status.value}")
            return False
            
        # 健康检查：使用次数过多
        from ...config import Config
        max_usage = Config.get_max_usage_count()
        if self.usage_count > max_usage:  # 使用动态限制，防止驱动连接问题
            self.logger.debug(f"实例 {self.instance_id} 不可用: 使用次数 {self.usage_count} > {max_usage}")
            return False
            
        # 健康检查：错误次数过多
        if self.error_count > 5:
            self.logger.debug(f"实例 {self.instance_id} 不可用: 错误次数 {self.error_count} > 5")
            return False
            
        return True
    
    def is_idle_too_long(self, max_idle_time: float) -> bool:
        """检查是否空闲时间过长"""
        if self.status != InstanceStatus.IDLE:
            return False
        
        idle_time = time.time() - self.last_used_at
        return idle_time > max_idle_time
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取实例指标"""
        current_time = time.time()
        return {
            'instance_id': self.instance_id,
            'status': self.status.value,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'last_used_at': datetime.fromtimestamp(self.last_used_at).isoformat(),
            'age_seconds': current_time - self.created_at,
            'idle_seconds': current_time - self.last_used_at if self.status == InstanceStatus.IDLE else 0,
            'usage_count': self.usage_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(1, self.usage_count),
            'is_connected': self.browser.is_connected() if self.browser else False,
            # 账户管理指标
            'account_usage_count': self.account_usage_count,
            'account_switch_threshold': self.account_switch_threshold,
            'current_account': self.current_account.username if self.current_account else None,
            'using_env_cookie': self.using_env_cookie
        }
    
    def set_account_manager(self, account_manager):
        """设置账户管理器引用"""
        self.account_manager = account_manager
        self.logger.info(f"实例 {self.instance_id} 已设置账户管理器")
    
    def increment_account_usage(self):
        """增加账户使用次数"""
        self.account_usage_count += 1
        self.logger.debug(f"实例 {self.instance_id} 账户使用次数: {self.account_usage_count}/{self.account_switch_threshold}")
    
    def should_switch_account(self) -> bool:
        """检查是否应该切换账户"""
        return self.account_usage_count >= self.account_switch_threshold
    
    async def check_and_switch_account(self) -> bool:
        """检查并执行账户切换"""
        if not self.should_switch_account():
            return False
        
        if not self.account_manager:
            self.logger.warning(f"实例 {self.instance_id} 未设置账户管理器，无法切换账户")
            return False
        
        try:
            if self.using_env_cookie:
                # 第一次切换：从环境变量cookie切换到管理账户
                await self._switch_to_managed_account()
            else:
                # 后续切换：在管理账户间轮询
                await self._switch_to_next_account()
            
            # 重置计数器
            self.account_usage_count = 0
            self.logger.info(f"实例 {self.instance_id} 账户切换成功，重置使用计数")
            return True
            
        except Exception as e:
            self.logger.error(f"实例 {self.instance_id} 账户切换失败: {e}")
            return False
    
    async def _switch_to_managed_account(self):
        """切换到管理系统账户"""
        if not self.current_context:
            raise RuntimeError("没有可用的浏览器上下文")
        
        # 获取下一个账户
        strategy = self._get_account_switch_strategy()
        next_account = self.account_manager.get_next_account(strategy=strategy)
        if not next_account:
            raise RuntimeError("没有可用的管理账户")
        
        # 导入AccountSwitcher
        from src.account_management import AccountSwitcher
        
        # 创建账户切换器并执行切换
        switcher = AccountSwitcher(self.account_manager)
        switch_result = await switcher.switch_to_account(
            self.current_context, 
            next_account.username,
            verify_login=self._get_account_login_verification()  # 从配置获取验证设置
        )
        
        if switch_result['success']:
            self.current_account = next_account
            self.using_env_cookie = False
            self.logger.info(f"实例 {self.instance_id} 成功切换到账户: {next_account.username}")
            
            # 账户切换成功后强制刷新页面 (模拟 Ctrl+R)
            if self.current_page:
                try:
                    self.logger.info(f"🔄 账户切换后强制刷新页面: {self.current_page.url}")
                    await self.current_page.reload(wait_until='domcontentloaded', timeout=10000)
                    # 给页面一些时间稳定
                    await asyncio.sleep(1)
                    self.logger.info("✅ 页面刷新完成，新账户内容已加载")
                except Exception as refresh_error:
                    self.logger.warning(f"账户切换后页面刷新失败: {refresh_error}")
        else:
            raise RuntimeError(f"切换到账户 {next_account.username} 失败: {switch_result.get('error_message')}")
    
    async def _switch_to_next_account(self):
        """切换到下一个管理账户"""
        if not self.current_context:
            raise RuntimeError("没有可用的浏览器上下文")
        
        # 获取下一个账户
        strategy = self._get_account_switch_strategy()
        next_account = self.account_manager.get_next_account(strategy=strategy)
        if not next_account:
            raise RuntimeError("没有可用的管理账户")
        
        # 导入AccountSwitcher
        from src.account_management import AccountSwitcher
        
        # 创建账户切换器并执行切换
        switcher = AccountSwitcher(self.account_manager)
        switch_result = await switcher.switch_to_account(
            self.current_context,
            next_account.username,
            verify_login=self._get_account_login_verification()  # 从配置获取验证设置
        )
        
        if switch_result['success']:
            self.current_account = next_account
            self.logger.info(f"实例 {self.instance_id} 成功切换到账户: {next_account.username}")
            
            # 账户切换成功后强制刷新页面 (模拟 Ctrl+R)
            if self.current_page:
                try:
                    self.logger.info(f"🔄 账户切换后强制刷新页面: {self.current_page.url}")
                    await self.current_page.reload(wait_until='domcontentloaded', timeout=10000)
                    # 给页面一些时间稳定
                    await asyncio.sleep(1)
                    self.logger.info("✅ 页面刷新完成，新账户内容已加载")
                except Exception as refresh_error:
                    self.logger.warning(f"账户切换后页面刷新失败: {refresh_error}")
        else:
            raise RuntimeError(f"切换到账户 {next_account.username} 失败: {switch_result.get('error_message')}")
    
    def get_account_status(self) -> Dict[str, Any]:
        """获取账户状态信息"""
        return {
            'instance_id': self.instance_id,
            'account_usage_count': self.account_usage_count,
            'account_switch_threshold': self.account_switch_threshold,
            'current_account': self.current_account.username if self.current_account else None,
            'using_env_cookie': self.using_env_cookie,
            'should_switch': self.should_switch_account(),
            'usage_progress': f"{self.account_usage_count}/{self.account_switch_threshold}"
        }
    
    async def _check_connection_health(self) -> bool:
        """检查浏览器连接健康状态"""
        try:
            # 最基本的检查：浏览器必须存在
            if not self.browser:
                return False
            
            # 检查浏览器连接
            try:
                # 尝试访问浏览器属性 - 简单的连接检查
                _ = self.browser.version
                # 尝试创建并立即关闭一个测试上下文
                test_context = await self.browser.new_context()
                await test_context.close()
            except Exception as e:
                self.logger.warning(f"实例 {self.instance_id} 浏览器连接失效: {e}")
                return False
            
            # 如果上下文和页面已经创建，则进行深度检查
            if self.current_context and self.current_page:
                try:
                    await self.current_page.evaluate("() => true")
                except Exception as e:
                    self.logger.warning(f"实例 {self.instance_id} 页面连接失效: {e}")
                    return False
            # 如果上下文和页面还未创建（新实例），则只要浏览器连接正常就认为健康
            
            return True
            
        except Exception as e:
            self.logger.error(f"实例 {self.instance_id} 健康检查失败: {e}")
            return False
    
    async def _force_restart(self):
        """强制重启实例"""
        try:
            self.logger.info(f"🔄 强制重启实例: {self.instance_id}")
            
            # 重置计数器
            self.usage_count = 0
            self.error_count = 0
            
            # 完全清理当前实例
            await self.dispose()
            
            # 重新初始化
            await self._initialize_browser()
            
            self.logger.info(f"✅ 实例 {self.instance_id} 重启完成")
            
        except Exception as e:
            self.logger.error(f"❌ 实例 {self.instance_id} 强制重启失败: {e}")
            self.status = InstanceStatus.ERROR
            raise