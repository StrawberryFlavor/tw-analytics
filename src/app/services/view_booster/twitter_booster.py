"""
Twitter多URL浏览量提升服务
基于scripts/twitter_booster.py，集成account_management模块，简化设计
"""

import asyncio
import logging
import signal
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, BrowserContext

from .proxy_pool import ProxyPool
from .screenshot_manager import ScreenshotManager, ScreenshotConfig, ScreenshotType, get_screenshot_config

# 修复导入路径 - account_management在src根目录下
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(src_path))

from account_management import AccountManager
from account_management.models import Account


@dataclass
class ViewBoosterConfig:
    """配置类"""
    target_urls: List[str] = field(default_factory=list)
    refresh_interval: int = 15  # 增加间隔避免频率限制
    max_concurrent_instances: int = 3
    max_tabs_per_instance: int = 3
    proxy: Optional[str] = None
    headless: bool = True
    use_proxy_pool: bool = False  # 是否使用代理池
    target_views: int = 100  # 目标浏览量，达到后自动停止
    
    # 截图配置
    screenshot_env: str = "production"  # production, staging, development, disabled


class MultiURLViewBooster:
    """多URL浏览量提升器 - 简化版本"""
    
    def __init__(self, config: ViewBoosterConfig, account_manager: AccountManager):
        self.config = config
        self.account_manager = account_manager
        self.logger = self._setup_logger()
        self.running = False
        self.instances = []
        self.stats = {
            'start_time': None,
            'total_views': 0,
            'successful_views': 0,
            'failed_views': 0,
            'errors': []
        }
        
        # 初始化截图管理器
        screenshot_config = get_screenshot_config(config.screenshot_env)
        self.screenshot_manager = ScreenshotManager(screenshot_config)
        screenshot_stats = self.screenshot_manager.get_stats()
        if screenshot_stats.get('enabled'):
            self.logger.info(f"📸 截图功能已启用 (环境: {config.screenshot_env})")
            if screenshot_stats.get('debug_mode'):
                self.logger.info(f"🔍 调试模式: 每{screenshot_config.debug_interval}次截图")
            else:
                self.logger.info(f"🎯 生产模式: 每{screenshot_config.milestone_interval}次里程碑截图")
        else:
            self.logger.info("❌ 截图功能已禁用")
        
        # 初始化代理池
        self.proxy_pool = ProxyPool(enabled=config.use_proxy_pool)
        if config.use_proxy_pool:
            stats = self.proxy_pool.get_stats()
            self.logger.info(f"🌐 代理池已启用: {stats['total_proxies']}个代理可用")
            if stats['total_proxies'] > 0:
                self.logger.info(f"📍 代理示例: {self.proxy_pool.proxies[0][:60]}...")
        else:
            self.logger.info("❌ 代理池已禁用")
        
        # 信号处理 - 只在主线程中设置
        try:
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
        except ValueError:
            # 非主线程中忽略信号设置
            self.logger.debug("无法在非主线程中设置信号处理器")
    
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def signal_handler(self, signum, _):
        self.logger.info(f"接收到信号 {signum}，准备停止...")
        self.running = False
    
    def _parse_proxy_url(self, proxy_string: str) -> Dict[str, Any]:
        """解析代理字符串，提取服务器和认证信息
        
        Args:
            proxy_string: 格式为 HOST:PORT:USER:PASS
        
        Returns:
            dict: Playwright代理配置
        """
        try:
            # 解析 HOST:PORT:USER:PASS 格式
            parts = proxy_string.strip().split(':')
            if len(parts) == 4:
                host, port, username, password = parts
                
                # 由于Playwright不支持SOCKS5认证，我们返回HTTP格式
                # 但实际使用时需要确保代理支持HTTP协议
                proxy_config = {
                    "server": f"http://{host}:{port}",
                    "username": username,
                    "password": password
                }
                return proxy_config
            else:
                raise ValueError(f"Invalid proxy format: {proxy_string}")
                
        except Exception as e:
            self.logger.error(f"代理解析失败: {e}")
            raise
    
    async def create_browser_instance(self, account: Account, instance_id: int, urls: List[str]):
        """创建浏览器实例（支持多标签页）"""
        try:
            self.logger.info(f"🔧 创建实例 {instance_id} ({account.username}) - 处理 {len(urls)} 个URL")
            
            playwright = await async_playwright().start()
            
            browser_args = {
                "headless": self.config.headless,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-default-apps",
                    "--no-proxy-server",  # 禁用系统代理
                    "--ignore-certificate-errors",  # 忽略证书错误
                    "--ignore-ssl-errors",  # 忽略SSL错误
                    "--disable-web-security",  # 禁用web安全（仅测试用）
                    "--disable-features=VizDisplayCompositor",  # 避免显示问题
                    "--disable-background-timer-throttling",  # 避免后台限制
                    "--disable-renderer-backgrounding",  # 避免渲染器后台化
                    "--disable-backgrounding-occluded-windows"  # 避免窗口后台化
                ]
            }
            
            # 获取代理配置（但不设置在browser_args中）
            proxy_config = None
            if self.config.use_proxy_pool and self.proxy_pool.is_enabled():
                # 使用代理池为每个实例分配不同代理
                proxy_url = self.proxy_pool.get_proxy_for_instance(instance_id)
                if proxy_url:
                    proxy_config = self._parse_proxy_url(proxy_url)
                    self.logger.info(f"🌐 实例 {instance_id} 将使用代理池代理: {proxy_config['server']}")
                else:
                    self.logger.warning(f"⚠️ 代理池启用但未获取到代理，实例 {instance_id} 将不使用代理")
            elif self.config.proxy:
                # 使用单一代理
                if not self.config.proxy.startswith(('http://', 'https://', 'socks5://')):
                    proxy_url = f"http://{self.config.proxy}"
                else:
                    proxy_url = self.config.proxy
                proxy_config = self._parse_proxy_url(proxy_url)
                self.logger.info(f"🌐 实例 {instance_id} 将使用单一代理: {proxy_config['server']}")
            
            if not proxy_config:
                self.logger.info(f"🚫 实例 {instance_id} 不使用代理")
            
            browser = await playwright.chromium.launch(**browser_args)
            
            # 创建上下文，代理配置只在这里设置
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            # 代理配置只在context中设置
            if proxy_config:
                context_args["proxy"] = proxy_config
                self.logger.info(f"✅ 实例 {instance_id} 代理配置已设置到browser context")
            
            context = await browser.new_context(**context_args)
            
            await self.setup_auth_token(context, account.auth_token)
            
            tabs = []
            for idx, url in enumerate(urls):
                page = await context.new_page()
                tab_info = {
                    'page': page,
                    'url': url,
                    'tab_id': f"{instance_id}-{idx}",
                    'views_count': 0,
                    'last_view_time': None,
                    'first_load': True
                }
                tabs.append(tab_info)
                self.logger.info(f"📑 创建标签页 {tab_info['tab_id']} -> {url}")
            
            instance = {
                'instance_id': instance_id,
                'account': account,
                'playwright': playwright,
                'browser': browser,
                'context': context,
                'tabs': tabs,
                'total_views': 0,
                'errors_count': 0
            }
            
            self.logger.info(f"✅ 实例 {instance_id} 创建成功，包含 {len(tabs)} 个标签页")
            return instance
            
        except Exception as e:
            self.logger.error(f"❌ 创建实例 {instance_id} 失败: {e}")
            return None
    
    async def setup_auth_token(self, context: BrowserContext, auth_token: str):
        """设置auth_token cookie"""
        try:
            cookies = [
                {
                    'name': 'auth_token',
                    'value': auth_token,
                    'domain': '.x.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': True,
                    'sameSite': 'None'
                },
                {
                    'name': 'auth_token', 
                    'value': auth_token,
                    'domain': '.twitter.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': True,
                    'sameSite': 'None'
                }
            ]
            
            await context.add_cookies(cookies)
            self.logger.debug(f"设置auth_token cookie: {auth_token[:10]}...")
            
        except Exception as e:
            self.logger.error(f"设置auth_token失败: {e}")
    
    async def view_tab(self, tab_info: Dict[str, Any], instance_id: int, username: str) -> bool:
        """访问单个标签页，带重试机制"""
        page = tab_info['page']
        url = tab_info['url']
        tab_id = tab_info['tab_id']
        
        self.logger.info(f"🔄 标签页 {tab_id} ({username}) 访问 {url}")
        
        # 重试机制：最多尝试3次
        for attempt in range(3):
            try:
                start_time = time.time()
                
                # 添加随机延迟避免频率限制
                if attempt > 0:
                    delay = random.uniform(3.0, 8.0) * (attempt + 1)
                    self.logger.info(f"⏰ 第{attempt + 1}次尝试，延迟{delay:.1f}秒...")
                    await asyncio.sleep(delay)
                
                # 智能截图：页面加载前状态（仅调试模式）
                if tab_info['views_count'] == 0:
                    should_screenshot, screenshot_type = await self.screenshot_manager.should_take_screenshot(
                        tab_id, 0, is_first=True
                    )
                    if should_screenshot and screenshot_type == ScreenshotType.DEBUG:
                        try:
                            await self.screenshot_manager.take_screenshot(
                                page, f"{tab_id}_preload", 0, ScreenshotType.DEBUG
                            )
                        except Exception as e:
                            self.logger.warning(f"加载前截图失败: {e}")
                
                if tab_info['first_load']:
                    self.logger.info(f"🌐 首次加载页面: {url}")
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    self.logger.info(f"📡 响应状态: {response.status if response else 'No response'}")
                    tab_info['first_load'] = False
                else:
                    self.logger.info(f"🔄 刷新页面: {url}")
                    response = await page.reload(wait_until="domcontentloaded", timeout=30000)
                    self.logger.info(f"📡 响应状态: {response.status if response else 'No response'}")
                
                # 检查页面URL和标题
                current_url = page.url
                title = await page.title()
                self.logger.info(f"📍 当前URL: {current_url}")
                self.logger.info(f"📄 页面标题: {title}")
                
                # 等待页面真正加载完成
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    self.logger.info(f"✅ 页面网络空闲")
                except Exception as e:
                    self.logger.warning(f"⚠️ 等待网络空闲超时: {e}")
                
                # 页面加载后随机等待
                await asyncio.sleep(random.uniform(3.0, 6.0))
                
                tab_info['views_count'] += 1
                
                # 智能截图判断
                is_first_success = tab_info['views_count'] == 1
                is_task_complete = self.stats['successful_views'] + 1 >= self.config.target_views
                
                should_screenshot, screenshot_type = await self.screenshot_manager.should_take_screenshot(
                    tab_id, 
                    tab_info['views_count'],
                    is_first=is_first_success,
                    is_final=is_task_complete
                )
                
                if should_screenshot:
                    try:
                        # 截图前稍等确保页面稳定
                        await asyncio.sleep(2)
                        
                        screenshot_path = await self.screenshot_manager.take_screenshot(
                            page, tab_id, tab_info['views_count'], screenshot_type
                        )
                        
                        # 如果是重要截图，同时保存HTML快照
                        if screenshot_type in [ScreenshotType.ERROR, ScreenshotType.FIRST_LOAD, ScreenshotType.FINAL]:
                            try:
                                content = await page.content()
                                html_path = screenshot_path.replace('.png', '.html') if screenshot_path else None
                                if html_path:
                                    with open(html_path, 'w', encoding='utf-8') as f:
                                        f.write(content[:20000])  # 保存前20000字符
                                    self.logger.debug(f"📝 HTML快照: {html_path}")
                            except Exception as html_error:
                                self.logger.debug(f"HTML保存失败: {html_error}")
                        
                    except Exception as screenshot_error:
                        self.logger.warning(f"截图失败: {screenshot_error}")
                
                tab_info['last_view_time'] = datetime.now()
                self.stats['total_views'] += 1
                self.stats['successful_views'] += 1
                
                # 标记账户已使用
                self.account_manager.mark_account_as_used(username)
                
                access_time = time.time() - start_time
                self.logger.info(f"✅ 标签页 {tab_id} 访问成功 (总计: {tab_info['views_count']}, 进度: {self.stats['successful_views']}/{self.config.target_views}, 用时: {access_time:.1f}s)")
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                if "ERR_CONNECTION_RESET" in error_msg:
                    self.logger.warning(f"⚠️ 标签页 {tab_id} 连接重置 (尝试 {attempt + 1}/3): {error_msg}")
                elif "ERR_PROXY_CONNECTION_FAILED" in error_msg:
                    self.logger.warning(f"⚠️ 标签页 {tab_id} 代理连接失败 (尝试 {attempt + 1}/3): {error_msg}")
                else:
                    self.logger.warning(f"⚠️ 标签页 {tab_id} 访问失败 (尝试 {attempt + 1}/3): {error_msg}")
                
                # 如果是最后一次尝试，记录为失败并可能截图
                if attempt == 2:
                    self.stats['failed_views'] += 1
                    self.logger.error(f"❌ 标签页 {tab_id} 三次尝试均失败")
                    
                    # 错误截图
                    try:
                        should_screenshot, screenshot_type = await self.screenshot_manager.should_take_screenshot(
                            tab_id, tab_info['views_count'], is_error=True
                        )
                        if should_screenshot:
                            await self.screenshot_manager.take_screenshot(
                                page, tab_id, tab_info['views_count'], screenshot_type, error_msg
                            )
                    except Exception as screenshot_error:
                        self.logger.debug(f"错误截图失败: {screenshot_error}")
                    
                    return False
        
        return False
    
    async def run_instance(self, instance: Dict[str, Any]):
        """运行单个实例（轮流访问多个标签页）"""
        instance_id = instance['instance_id']
        account = instance['account']
        tabs = instance['tabs']
        
        self.logger.info(f"🚀 启动实例 {instance_id} ({account.username})，管理 {len(tabs)} 个标签页")
        
        try:
            while (self.running and 
                   self.stats['successful_views'] < self.config.target_views):
                for tab_info in tabs:
                    if not self.running or self.stats['successful_views'] >= self.config.target_views:
                        break
                    
                    await self.view_tab(tab_info, instance_id, account.username)
                    
                    # 检查是否达到目标
                    if self.stats['successful_views'] >= self.config.target_views:
                        self.logger.info(f"🎯 已达到目标浏览量 {self.config.target_views}，停止实例 {instance_id}")
                        break
                    
                    if self.running:
                        await asyncio.sleep(self.config.refresh_interval / len(tabs))
                
                instance['total_views'] = sum(tab['views_count'] for tab in tabs)
                
        except Exception as e:
            self.logger.error(f"实例 {instance_id} 运行异常: {e}")
        
        finally:
            await self.cleanup_instance(instance)
    
    async def cleanup_instance(self, instance: Dict[str, Any]):
        """清理实例资源"""
        try:
            instance_id = instance['instance_id']
            self.logger.info(f"🧹 清理实例 {instance_id}")
            
            for tab_info in instance.get('tabs', []):
                if 'page' in tab_info and tab_info['page']:
                    await tab_info['page'].close()
            
            if 'context' in instance and instance['context']:
                await instance['context'].close()
            if 'browser' in instance and instance['browser']:
                await instance['browser'].close()
            if 'playwright' in instance and instance['playwright']:
                await instance['playwright'].stop()
                
        except Exception as e:
            self.logger.error(f"清理实例 {instance['instance_id']} 时出错: {e}")
    
    def distribute_urls(self, urls: List[str], num_instances: int, max_tabs: int) -> List[List[str]]:
        """分配URL到不同的实例"""
        distribution = []
        
        # 为每个实例分配URL，即使URL数量少于实例数也要重复分配
        for i in range(num_instances):
            instance_urls = []
            for j in range(max_tabs):
                # 使用轮询方式分配URL
                url_index = (i * max_tabs + j) % len(urls)
                instance_urls.append(urls[url_index])
            
            distribution.append(instance_urls)
        
        return distribution
    
    async def start_boost(self, urls: List[str]) -> Dict[str, Any]:
        """启动多URL浏览量提升"""
        self.logger.info("🎯 Twitter多URL浏览量提升器启动")
        
        if not urls:
            return {"success": False, "error": "没有配置目标URL"}
        
        # 获取活跃账户
        active_accounts = self.account_manager.get_active_accounts()
        if not active_accounts:
            return {"success": False, "error": "没有可用的活跃账户"}
        
        self.config.target_urls = urls
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        num_urls = len(urls)
        max_instances = min(self.config.max_concurrent_instances, len(active_accounts))
        
        url_distribution = self.distribute_urls(urls, max_instances, self.config.max_tabs_per_instance)
        
        self.logger.info(f"📋 配置信息:")
        self.logger.info(f"   总URL数: {num_urls}")
        self.logger.info(f"   使用账户数: {max_instances}")
        self.logger.info(f"   每实例最大标签页: {self.config.max_tabs_per_instance}")
        self.logger.info(f"   刷新间隔: {self.config.refresh_interval}秒")
        
        # 创建浏览器实例
        creation_tasks = []
        for i, urls_subset in enumerate(url_distribution):
            if i < len(active_accounts):
                account = active_accounts[i]
                creation_tasks.append(self.create_browser_instance(account, i, urls_subset))
        
        created_instances = await asyncio.gather(*creation_tasks, return_exceptions=True)
        
        self.instances = [
            instance for instance in created_instances 
            if instance is not None and not isinstance(instance, Exception)
        ]
        
        if not self.instances:
            return {"success": False, "error": "没有成功创建任何浏览器实例"}
        
        total_tabs = sum(len(inst['tabs']) for inst in self.instances)
        self.logger.info(f"✅ 成功创建 {len(self.instances)} 个浏览器实例，共 {total_tabs} 个标签页")
        
        # 启动所有实例
        try:
            tasks = [self.run_instance(instance) for instance in self.instances]
            await asyncio.gather(*tasks)
            
        except Exception as e:
            self.logger.error(f"程序运行异常: {e}")
        
        finally:
            await self.stop()
        
        return {
            "success": True,
            "stats": self.stats,
            "instances_used": len(self.instances),
            "total_tabs": total_tabs
        }
    
    async def stop(self):
        """停止程序"""
        self.running = False
        self.logger.info("正在停止所有实例...")
        
        # 截图管理器清理
        await self.screenshot_manager.cleanup()
        
        if self.stats['start_time']:
            duration = (datetime.now() - self.stats['start_time']).total_seconds()
            self.logger.info(f"\n📊 运行统计:")
            self.logger.info(f"   运行时长: {duration:.1f}秒")
            self.logger.info(f"   总访问次数: {self.stats['total_views']}")
            self.logger.info(f"   成功访问: {self.stats['successful_views']}")
            self.logger.info(f"   失败访问: {self.stats['failed_views']}")
            
            if self.stats['total_views'] > 0:
                success_rate = self.stats['successful_views'] / self.stats['total_views'] * 100
                self.logger.info(f"   成功率: {success_rate:.1f}%")
            
            # 显示截图统计
            screenshot_stats = self.screenshot_manager.get_stats()
            if screenshot_stats.get('enabled'):
                self.logger.info(f"\n📸 截图统计:")
                self.logger.info(f"   截图环境: {self.config.screenshot_env}")
                self.logger.info(f"   生成截图: {screenshot_stats.get('total_screenshots', 0)}")
                self.logger.info(f"   存储占用: {screenshot_stats.get('storage_mb', 0)}MB")
                self.logger.info(f"   文件总数: {screenshot_stats.get('total_files', 0)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        stats['screenshot_stats'] = self.screenshot_manager.get_stats()
        return stats