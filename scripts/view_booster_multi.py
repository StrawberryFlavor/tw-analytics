#!/usr/bin/env python3
"""
Twitter多推文浏览量提升脚本 - 优化版
支持一个账户同时处理多个推文URL，提高资源利用率
"""

import asyncio
import json
import logging
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, BrowserContext
import random


@dataclass
class ViewBoosterConfig:
    """配置类"""
    target_urls: List[str] = field(default_factory=list)  # 支持多个URL
    refresh_interval: int = 10  # 每个标签页的刷新间隔
    max_concurrent_instances: int = 3  # 最大并发浏览器实例数
    max_tabs_per_instance: int = 3  # 每个实例的最大标签页数
    accounts_config_path: str = "accounts.json"  # 账户配置文件路径
    proxy: Optional[str] = None  # 代理地址
    headless: bool = True  # 是否无头模式
    accounts: List[Any] = field(default_factory=list)  # 账户列表
    
    def __post_init__(self):
        """初始化后加载账户"""
        self.load_accounts()
    
    def load_accounts(self):
        """加载账户配置"""
        script_dir = Path(__file__).parent
        accounts_path = script_dir / self.accounts_config_path
        
        if accounts_path.exists():
            with open(accounts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                accounts_data = data.get('accounts', [])
                
                # 解析账户数据
                from collections import namedtuple
                Account = namedtuple('Account', ['username', 'password', 'email', 'auth_token', 'status'])
                
                self.accounts = []
                for acc in accounts_data:
                    if acc.get('status') == 'active' and acc.get('auth_token'):
                        account = Account(
                            username=acc.get('username'),
                            password=acc.get('password'),
                            email=acc.get('email'),
                            auth_token=acc.get('auth_token'),
                            status=acc.get('status')
                        )
                        self.accounts.append(account)
                
                print(f"✅ 加载了 {len(self.accounts)} 个活跃账户")
        else:
            print(f"❌ 账户配置文件不存在: {accounts_path}")


class MultiURLViewBooster:
    """多URL浏览量提升器"""
    
    def __init__(self, config: ViewBoosterConfig):
        self.config = config
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
        
        # 信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def signal_handler(self, signum, _):
        """信号处理"""
        self.logger.info(f"接收到信号 {signum}，准备停止...")
        self.running = False
    
    async def create_browser_instance(self, account, instance_id: int, urls: List[str]):
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
                    "--disable-default-apps"
                ]
            }
            
            # 代理配置
            if self.config.proxy:
                if not self.config.proxy.startswith(('http://', 'https://', 'socks5://')):
                    proxy_url = f"http://{self.config.proxy}"
                else:
                    proxy_url = self.config.proxy
                browser_args["proxy"] = {"server": proxy_url}
                self.logger.info(f"实例 {instance_id} 使用代理: {proxy_url}")
            
            browser = await playwright.chromium.launch(**browser_args)
            
            # 创建上下文
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # 设置auth_token cookie
            await self.setup_auth_token(context, account.auth_token)
            
            # 创建多个标签页
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
        """访问单个标签页"""
        try:
            page = tab_info['page']
            url = tab_info['url']
            tab_id = tab_info['tab_id']
            
            self.logger.info(f"🔄 标签页 {tab_id} ({username}) 访问 {url}")
            
            start_time = time.time()
            
            if tab_info['first_load']:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                tab_info['first_load'] = False
            else:
                await page.reload(wait_until="domcontentloaded", timeout=15000)
            
            # 简单等待
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # 更新统计
            tab_info['views_count'] += 1
            tab_info['last_view_time'] = datetime.now()
            self.stats['total_views'] += 1
            self.stats['successful_views'] += 1
            
            access_time = time.time() - start_time
            self.logger.info(f"✅ 标签页 {tab_id} 访问成功 (总计: {tab_info['views_count']}, 用时: {access_time:.1f}s)")
            
            return True
            
        except Exception as e:
            self.stats['failed_views'] += 1
            self.logger.error(f"❌ 标签页 {tab_info['tab_id']} 访问失败: {e}")
            return False
    
    async def run_instance(self, instance: Dict[str, Any]):
        """运行单个实例（轮流访问多个标签页）"""
        instance_id = instance['instance_id']
        account = instance['account']
        tabs = instance['tabs']
        
        self.logger.info(f"🚀 启动实例 {instance_id} ({account.username})，管理 {len(tabs)} 个标签页")
        
        try:
            while self.running:
                # 轮流访问每个标签页
                for tab_info in tabs:
                    if not self.running:
                        break
                    
                    await self.view_tab(tab_info, instance_id, account.username)
                    
                    # 标签页之间的间隔（避免太频繁）
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
            
            # 关闭所有标签页
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
        # 如果URL数量少于实例数，每个实例分配所有URL（直到max_tabs限制）
        if len(urls) <= max_tabs:
            # 所有实例都处理相同的URL集合
            return [urls for _ in range(min(num_instances, len(self.config.accounts)))]
        
        # 如果URL数量多于max_tabs，需要分配
        # 每个实例最多处理max_tabs个URL
        distribution = []
        url_index = 0
        
        for i in range(num_instances):
            instance_urls = []
            for j in range(max_tabs):
                if url_index < len(urls):
                    instance_urls.append(urls[url_index])
                    url_index += 1
                else:
                    # 如果URL用完了，从头开始循环分配
                    instance_urls.append(urls[url_index % len(urls)])
                    url_index += 1
            
            if instance_urls:
                distribution.append(instance_urls)
        
        return distribution
    
    async def start(self):
        """启动多URL浏览量提升程序"""
        self.logger.info("🎯 Twitter多URL浏览量提升器启动")
        self.logger.warning("⚠️  请确保遵守Twitter服务条款，仅用于合法测试目的")
        
        if not self.config.target_urls:
            self.logger.error("❌ 没有配置目标URL")
            return
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        # 计算实例数和URL分配
        num_urls = len(self.config.target_urls)
        max_instances = min(
            self.config.max_concurrent_instances,
            len(self.config.accounts)
        )
        
        # 分配URL到各个实例
        url_distribution = self.distribute_urls(
            self.config.target_urls,
            max_instances,
            self.config.max_tabs_per_instance
        )
        
        self.logger.info(f"📋 配置信息:")
        self.logger.info(f"   总URL数: {num_urls}")
        self.logger.info(f"   使用账户数: {max_instances}")
        self.logger.info(f"   每实例最大标签页: {self.config.max_tabs_per_instance}")
        self.logger.info(f"   刷新间隔: {self.config.refresh_interval}秒")
        self.logger.info(f"   URL分配方案: {[len(urls) for urls in url_distribution]}")
        
        # 创建浏览器实例
        self.logger.info("🔧 创建浏览器实例...")
        creation_tasks = []
        for i, urls in enumerate(url_distribution):
            if i < len(self.config.accounts):
                account = self.config.accounts[i]
                creation_tasks.append(self.create_browser_instance(account, i, urls))
        
        created_instances = await asyncio.gather(*creation_tasks, return_exceptions=True)
        
        # 过滤成功创建的实例
        self.instances = [
            instance for instance in created_instances 
            if instance is not None and not isinstance(instance, Exception)
        ]
        
        if not self.instances:
            self.logger.error("❌ 没有成功创建任何浏览器实例，程序退出")
            return
        
        total_tabs = sum(len(inst['tabs']) for inst in self.instances)
        self.logger.info(f"✅ 成功创建 {len(self.instances)} 个浏览器实例，共 {total_tabs} 个标签页")
        
        # 启动所有实例
        try:
            tasks = [self.run_instance(instance) for instance in self.instances]
            await asyncio.gather(*tasks)
            
        except KeyboardInterrupt:
            self.logger.info("用户中断程序")
        except Exception as e:
            self.logger.error(f"程序运行异常: {e}")
        
        finally:
            await self.stop()
    
    async def stop(self):
        """停止程序"""
        self.running = False
        self.logger.info("正在停止所有实例...")
        
        # 输出统计信息
        if self.stats['start_time']:
            duration = (datetime.now() - self.stats['start_time']).total_seconds()
            self.logger.info(f"\n📊 运行统计:")
            self.logger.info(f"   运行时长: {duration:.1f}秒")
            self.logger.info(f"   总访问次数: {self.stats['total_views']}")
            self.logger.info(f"   成功访问: {self.stats['successful_views']}")
            self.logger.info(f"   失败访问: {self.stats['failed_views']}")
            
            if self.stats['total_views'] > 0:
                success_rate = self.stats['successful_views'] / self.stats['total_views'] * 100
                avg_view_time = duration / self.stats['total_views'] if self.stats['total_views'] > 0 else 0
                self.logger.info(f"   成功率: {success_rate:.1f}%")
                self.logger.info(f"   平均访问间隔: {avg_view_time:.1f}秒")


async def main():
    """主函数"""
    print("🌟 Twitter多URL浏览量提升工具 (优化版)")
    print("=" * 50)
    
    # 方式1：交互式输入（默认）
    # 收集多个URL
    urls = []
    print("\n📝 请输入要刷新的推文URL（每行一个，输入空行结束）:")
    
    while True:
        url = input(f"URL {len(urls) + 1}: ").strip()
        if not url:
            if urls:
                break
            else:
                print("❌ 至少需要输入一个URL")
                continue
        
        if 'twitter.com' in url or 'x.com' in url:
            urls.append(url)
        else:
            print("❌ 请输入有效的Twitter/X URL")
    
    # 方式2：直接配置（取消下面的注释并注释掉上面的交互式输入）
    # urls = [
    #     "https://x.com/username/status/1234567890",
    #     "https://x.com/username/status/0987654321",
    #     "https://x.com/username/status/1111111111",
    #     # 添加更多URL...
    # ]
    
    # 其他配置
    try:
        max_instances = int(input("\n🔢 请输入最大并发实例数(默认3): ").strip() or "3")
    except ValueError:
        max_instances = 3
        print("⚠️  输入无效，使用默认并发数3")
    
    try:
        max_tabs = int(input("🔢 每个实例的最大标签页数(默认3): ").strip() or "3")
    except ValueError:
        max_tabs = 3
        print("⚠️  输入无效，使用默认标签页数3")
    
    try:
        refresh_interval = int(input("⏱️  请输入刷新间隔秒数(默认10): ").strip() or "10")
    except ValueError:
        refresh_interval = 10
        print("⚠️  输入无效，使用默认间隔10秒")
    
    proxy = input("🌐 请输入代理地址(留空不使用): ").strip() or None
    
    headless = input("👻 是否使用无头模式? (y/N): ").strip().lower() in ['y', 'yes']
    
    # 创建配置
    config = ViewBoosterConfig(
        target_urls=urls,
        refresh_interval=refresh_interval,
        max_concurrent_instances=max_instances,
        max_tabs_per_instance=max_tabs,
        proxy=proxy,
        headless=headless
    )
    
    if not config.accounts:
        print("❌ 没有可用的账户，请检查accounts.json文件")
        return
    
    # 计算资源使用情况
    actual_instances = min(max_instances, len(config.accounts), len(urls))
    total_tabs = min(len(urls), actual_instances * max_tabs)
    
    print(f"\n📊 资源分配预览:")
    print(f"   将创建 {actual_instances} 个浏览器实例")
    print(f"   总共 {total_tabs} 个标签页处理 {len(urls)} 个URL")
    print(f"   每个标签页约 {refresh_interval}秒刷新一次")
    
    confirm = input("\n🚀 是否开始运行? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("已取消运行")
        return
    
    # 启动提升器
    booster = MultiURLViewBooster(config)
    await booster.start()


if __name__ == "__main__":
    asyncio.run(main())
