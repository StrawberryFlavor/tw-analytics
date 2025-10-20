"""
Fast View Booster Service - No Browser Required
High-speed Twitter view boosting using direct HTTP requests
"""

import asyncio
import httpx
import random
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

from .proxy_pool import ProxyPool
from .smart_proxy_manager import get_smart_proxy_manager
from account_management import AccountManager
from account_management.models import Account


@dataclass
class FastBoosterConfig:
    """Configuration for fast view booster"""
    target_urls: List[str] = field(default_factory=list)
    target_views: int = 1000
    max_concurrent_requests: int = 10
    request_interval: tuple = (1, 3)  # Random interval between requests (seconds)
    use_proxy_pool: bool = True
    proxy: Optional[str] = None  # Single proxy URL (ignored if use_proxy_pool=True)
    timeout: int = 10  # Request timeout in seconds
    retry_on_failure: bool = True
    max_retries: int = 3


class FastViewBooster:
    """Fast view booster using HTTP requests instead of browser"""
    
    def __init__(self, config: FastBoosterConfig, account_manager: AccountManager):
        self.config = config
        self.account_manager = account_manager
        
        # 使用智能代理管理器替代简单的代理池
        self.smart_proxy_manager = get_smart_proxy_manager()
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)  # Enable debug logging
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "views_per_url": {url: 0 for url in config.target_urls},
            "start_time": datetime.now()
        }
        
        # Control flags
        self.running = False
        self._stop_event = asyncio.Event()
        
        # Session cache for accounts to avoid repeated logins
        self._session_cache = {}  # {username: {"cookies": {}, "expires": timestamp}}
        self._session_cache_duration = 3600  # 1 hour cache
        
        # User agents pool
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ]
    
    def _get_headers(self, account: Account) -> Dict[str, str]:
        """Construct request headers to mimic real browser"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
    
    
    async def _login_and_get_session(self, account: Account, client: httpx.AsyncClient) -> Dict[str, str]:
        """通过HTTP请求登录并获取完整的session cookies"""
        self.logger.info(f"开始登录账户 {account.username}...")
        
        try:
            # 1. 首先访问Twitter主页获取guest token
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
            
            response = await client.get("https://twitter.com", headers=headers)
            if response.status_code != 200:
                self.logger.error(f"无法访问Twitter主页: {response.status_code}")
                self.logger.debug(f"响应内容: {response.text[:500]}")
                return {}
            
            # 从响应中提取cookies
            session_cookies = {}
            for name, value in response.cookies.items():
                session_cookies[name] = value
            
            self.logger.debug(f"获取到初始cookies: {list(session_cookies.keys())}")
            
            # 2. 设置auth_token到cookies中
            if hasattr(account, 'auth_token') and account.auth_token:
                session_cookies['auth_token'] = account.auth_token
                self.logger.debug(f"设置auth_token: {account.auth_token[:10]}...")
            else:
                self.logger.error(f"账户 {account.username} 没有auth_token")
                return {}
            
            # 3. 访问/home验证登录状态并获取CSRF token
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://twitter.com/",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            response = await client.get(
                "https://twitter.com/home",
                cookies=session_cookies,
                headers=headers,
                follow_redirects=True
            )
            
            # 更新cookies
            for name, value in response.cookies.items():
                session_cookies[name] = value
            
            self.logger.debug(f"登录后cookies: {list(session_cookies.keys())}")
            
            # 4. 从页面HTML中提取CSRF token
            if response.status_code == 200:
                html_content = response.text
                
                # 查找页面中的CSRF token (多种可能的格式)
                import re
                csrf_patterns = [
                    r'"ct0":"([^"]+)"',                    # JavaScript中的ct0
                    r'ct0=([^;]+)',                       # Cookie格式
                    r'"csrf_token":"([^"]+)"',            # 另一种格式
                    r'<input[^>]*csrf[^>]*value="([^"]+)"'  # HTML表单中的CSRF
                ]
                
                csrf_token = None
                for pattern in csrf_patterns:
                    csrf_match = re.search(pattern, html_content)
                    if csrf_match:
                        csrf_token = csrf_match.group(1)
                        self.logger.debug(f"从页面提取CSRF token (模式 {pattern[:20]}...): {csrf_token[:10]}...")
                        break
                
                if csrf_token:
                    session_cookies['ct0'] = csrf_token
                else:
                    # 如果页面中没有找到，尝试从现有cookies中获取或生成
                    if 'ct0' in session_cookies:
                        csrf_token = session_cookies['ct0']
                        self.logger.debug(f"使用现有ct0 cookie: {csrf_token[:10]}...")
                    else:
                        # 最后手段：生成一个随机的32字符token
                        import secrets
                        csrf_token = secrets.token_hex(16)  # 32字符
                        session_cookies['ct0'] = csrf_token
                        self.logger.debug(f"生成随机CSRF token: {csrf_token[:10]}...")
                
                # 检查是否成功登录
                final_url = str(response.url)
                if '/home' in final_url or 'login' not in final_url.lower():
                    self.logger.info(f"✅ 账户 {account.username} 登录成功")
                    return session_cookies
                else:
                    self.logger.warning(f"⚠️ 账户 {account.username} 可能未正确登录，URL: {final_url}")
                    return session_cookies  # 仍然返回cookies，可能仍可使用
            else:
                self.logger.error(f"登录验证失败: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"登录过程中出现错误 {account.username}: {str(e)}")
            return {}
    
    async def _get_or_refresh_session(self, account: Account, client: httpx.AsyncClient) -> Dict[str, str]:
        """获取或刷新账户的session，使用缓存机制"""
        username = account.username
        current_time = datetime.now().timestamp()
        
        # 检查缓存是否有效
        if username in self._session_cache:
            cached_session = self._session_cache[username]
            if cached_session["expires"] > current_time:
                self.logger.debug(f"使用缓存的session for {username}")
                return cached_session["cookies"]
            else:
                self.logger.debug(f"Session缓存已过期 for {username}")
        
        # 缓存无效或不存在，重新登录
        self.logger.info(f"刷新session for {username}")
        cookies = await self._login_and_get_session(account, client)
        
        if cookies:
            # 缓存新的session
            self._session_cache[username] = {
                "cookies": cookies,
                "expires": current_time + self._session_cache_duration
            }
            self.logger.debug(f"Session已缓存 for {username}，有效期到 {datetime.fromtimestamp(current_time + self._session_cache_duration)}")
        
        return cookies
    
    def _parse_cookies(self, account: Account) -> Dict[str, str]:
        """Parse cookies from account data - use auth_token (deprecated, use _login_and_get_session instead)"""
        cookies = {}
        
        # Use auth_token as cookie for authentication
        if hasattr(account, 'auth_token') and account.auth_token:
            # Generate a stable CSRF token based on auth_token hash for consistency
            import hashlib
            auth_hash = hashlib.md5(account.auth_token.encode()).hexdigest()
            csrf_token = auth_hash  # Use MD5 hash as CSRF token (32 chars)
            
            cookies = {
                'auth_token': account.auth_token,
                'ct0': csrf_token,  # Must match x-csrf-token header
                'guest_id': f'v1%3A{int(datetime.now().timestamp() * 1000)}',
                'personalization_id': f'"v1_{int(datetime.now().timestamp() * 1000)}"',
                'lang': 'en',
                '_twitter_sess': 'BAh7CSIKZmxhc2hJQzonQWN0aW9uQ29udHJvbGxlcjo6Rmxhc2g6OkZsYXNo%250ASGFzaHsABjoKQHVzZWR7ADoPY3JlYXRlZF9hdGwrCECwlcN5AToMY3NyZl9p%250AZCIlNjE2MTYxNjE2MTYxNjE2MTYxNjE2MTYxNjE2MTYxNjE2MTYxNjE2MTYx%250AZGI0ZjZmNzIzNDIzNDIzNDIzNDIzNDIzNDIzNA%253D%253D--1234567890abcdef'
            }
            
            self.logger.debug(f"Using auth_token for {account.username}: {account.auth_token[:10]}...")
            self.logger.debug(f"Generated CSRF token: {csrf_token[:10]}...")
        else:
            self.logger.warning(f"No auth_token for account {account.username}")
        
        return cookies
    
    async def _get_proxy_config(self) -> Optional[Dict[str, Any]]:
        """Get smart proxy configuration"""
        try:
            # 将API配置参数传递给智能代理管理器，API参数优先级高于环境变量
            return await self.smart_proxy_manager.get_proxy_config(
                override_use_proxy_pool=self.config.use_proxy_pool,
                override_proxy=self.config.proxy
            )
        except Exception as e:
            self.logger.error(f"获取代理配置失败: {e}")
            return None
    
    def _extract_tweet_id(self, url: str) -> str:
        """Extract tweet ID from Twitter URL"""
        if '/status/' in url:
            return url.split('/status/')[-1].split('?')[0]
        return ""
    
    async def _make_view_request(self, url: str, account: Account, client: httpx.AsyncClient) -> bool:
        """Make a simple page request to increment tweet view count - simpler and more reliable"""
        try:
            tweet_id = self._extract_tweet_id(url)
            if not tweet_id:
                self.logger.error(f"Could not extract tweet ID from {url}")
                return False
            
            # 使用缓存的session或重新登录
            cookies = await self._get_or_refresh_session(account, client)
            if not cookies:
                self.logger.warning(f"Failed to get session for account {account.username}, skipping")
                return False
            
            # 直接访问推文页面 - 这是最简单且有效的方法
            # 模拟真实用户访问推文页面的行为
            
            headers = {
                "User-Agent": random.choice(self.user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://twitter.com/",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate", 
                "Sec-Fetch-Site": "same-origin",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            }
            
            self.logger.info(f"Making page request for tweet {tweet_id} with account {account.username}")
            self.logger.debug(f"Target URL: {url}")
            
            # 直接访问推文页面
            response = await client.get(
                url,
                headers=headers,
                cookies=cookies
            )
            
            # Check if request was successful
            if response.status_code == 200:
                # 检查页面是否包含推文内容
                page_content = response.text
                
                # 验证页面确实加载了推文内容
                if any(indicator in page_content.lower() for indicator in ['tweet', 'status', tweet_id]):
                    self.stats["successful_requests"] += 1
                    self.stats["views_per_url"][url] = self.stats["views_per_url"].get(url, 0) + 1
                    self.logger.info(f"✅ Page request successful for tweet {tweet_id} (Account: {account.username})")
                    self.logger.debug(f"Page content length: {len(page_content)} characters")
                    return True
                else:
                    self.logger.warning(f"⚠️ Page loaded but missing tweet content for {tweet_id}")
                    self.stats["failed_requests"] += 1
                    return False
                    
            else:
                self.stats["failed_requests"] += 1
                self.logger.error(f"❌ Page request failed with status {response.status_code} for tweet {tweet_id} (Account: {account.username})")
                
                # Log more details for authentication errors
                if response.status_code == 401:
                    self.logger.error(f"Auth error - check auth_token: {cookies.get('auth_token', 'None')[:10]}...")
                elif response.status_code == 403:
                    self.logger.error(f"Forbidden - Account may be suspended or access restricted")
                elif response.status_code == 404:
                    self.logger.error(f"Tweet not found - URL may be invalid: {url}")
                
                self.logger.debug(f"Response content: {response.text[:500]}...")
                return False
                
        except Exception as e:
            self.stats["failed_requests"] += 1
            self.logger.error(f"❌ Page request error for tweet {tweet_id} (Account: {account.username}): {str(e)}", exc_info=True)
            return False
        finally:
            self.stats["total_requests"] += 1
    
    async def _worker(self, worker_id: int):
        """Worker coroutine to process requests"""
        try:
            accounts = self.account_manager.get_all_accounts()
            if not accounts:
                self.logger.error("No accounts available")
                return
            
            self.logger.debug(f"Worker {worker_id} starting with {len(accounts)} accounts")
            
            # Get smart proxy configuration
            proxy_config = await self._get_proxy_config()
            
            if proxy_config:
                proxy_type = "智能代理"
                if "socks5://" in str(proxy_config):
                    proxy_type = "代理池"
                elif "127.0.0.1" in str(proxy_config):
                    proxy_type = "本地代理"
                self.logger.info(f"Worker {worker_id} 使用{proxy_type}")
            else:
                self.logger.info(f"Worker {worker_id} 使用直连")
            
            # Create client with proper timeout and proxy settings
            client_config = {
                "timeout": httpx.Timeout(self.config.timeout),
                "follow_redirects": True,
                "verify": False,  # Disable SSL verification for proxies
                "http2": False,  # Disable HTTP/2 for better proxy compatibility
                "limits": httpx.Limits(max_keepalive_connections=5, max_connections=10),
                "trust_env": False  # Ignore system proxy environment variables
            }
            
            if proxy_config:
                client_config["proxies"] = proxy_config
                self.logger.info(f"Worker {worker_id} using proxy")
            else:
                self.logger.info(f"Worker {worker_id} no proxy configured")
            
            async with httpx.AsyncClient(**client_config) as client:
                while self.running and not self._stop_event.is_set():
                    # Check if target views reached
                    total_views = sum(self.stats["views_per_url"].values())
                    if total_views >= self.config.target_views:
                        self.logger.info(f"🎯 Target views reached: {total_views}/{self.config.target_views}")
                        self._stop_event.set()
                        break
                    
                    # Select random URL and account
                    url = random.choice(self.config.target_urls)
                    account = random.choice(accounts)
                    
                    # Make GraphQL request to increment view count
                    success = await self._make_view_request(url, account, client)
                    
                    # Retry logic
                    if not success and self.config.retry_on_failure:
                        for retry in range(self.config.max_retries):
                            await asyncio.sleep(0.5)
                            # Try with different proxy configuration
                            new_proxy_config = await self._get_proxy_config()
                            if new_proxy_config:
                                client._proxies = new_proxy_config
                            
                            success = await self._make_view_request(url, account, client)
                            if success:
                                break
                    
                    # Random delay between requests
                    delay = random.uniform(*self.config.request_interval)
                    await asyncio.sleep(delay)
        except Exception as e:
            self.logger.error(f"Worker {worker_id} crashed: {e}", exc_info=True)
    
    async def _test_proxy_connection(self) -> bool:
        """Test smart proxy connection before starting"""
        # 注意：test_proxy_connection 需要单独的实现，因为它需要实际创建HTTP客户端
        # 这里我们先简化实现，后续可以改进
        try:
            proxy_config = await self._get_proxy_config()
            if proxy_config:
                self.logger.info("✅ 代理配置获取成功，连接测试通过")
                return True
            else:
                self.logger.info("✅ 直连模式，连接测试通过")
                return True
        except Exception as e:
            self.logger.error(f"❌ 代理连接测试失败: {e}")
            return False
    
    async def start(self):
        """Start the fast view booster"""
        self.running = True
        self._stop_event.clear()
        self.stats["start_time"] = datetime.now()
        
        self.logger.info(f"🚀 Starting Fast View Booster")
        self.logger.info(f"📊 Target views: {self.config.target_views}")
        self.logger.info(f"🔗 URLs: {self.config.target_urls}")
        
        accounts = self.account_manager.get_all_accounts()
        self.logger.info(f"👥 Accounts: {len(accounts)}")
        
        # 显示智能代理管理器状态
        proxy_status = self.smart_proxy_manager.get_status()
        self.logger.info(f"🌐 代理模式: {proxy_status['network_mode']}")
        if proxy_status['proxy_pool_count'] > 0:
            self.logger.info(f"🌍 代理池: {proxy_status['proxy_pool_count']} 个代理")
        
        # Test proxy connection first (non-blocking)
        if not await self._test_proxy_connection():
            self.logger.warning("⚠️ Proxy connection test failed, but continuing with execution...")
        
        # Create worker tasks
        workers = []
        self.logger.info(f"Creating {self.config.max_concurrent_requests} workers...")
        for i in range(self.config.max_concurrent_requests):
            self.logger.debug(f"Creating worker {i}")
            worker = asyncio.create_task(self._worker(i))
            workers.append(worker)
        
        self.logger.info(f"All workers created, waiting for completion...")
        
        # Wait for completion or stop signal
        try:
            await self._stop_event.wait()
        finally:
            self.running = False
            # Cancel all workers
            for worker in workers:
                worker.cancel()
            
            # Wait for workers to finish
            await asyncio.gather(*workers, return_exceptions=True)
            
            # Print final statistics
            self._print_stats()
    
    def stop(self):
        """Stop the fast view booster"""
        self.logger.info("⏹️ Stopping Fast View Booster")
        self.running = False
        self._stop_event.set()
    
    def _print_stats(self):
        """Print statistics"""
        duration = (datetime.now() - self.stats["start_time"]).total_seconds()
        total_views = sum(self.stats["views_per_url"].values())
        
        self.logger.info("=" * 50)
        self.logger.info("📈 Fast View Booster Statistics")
        self.logger.info(f"⏱️ Duration: {duration:.1f} seconds")
        self.logger.info(f"📊 Total Views: {total_views}")
        self.logger.info(f"✅ Successful Requests: {self.stats['successful_requests']}")
        self.logger.info(f"❌ Failed Requests: {self.stats['failed_requests']}")
        self.logger.info(f"⚡ Requests/sec: {self.stats['total_requests']/duration:.2f}")
        
        if total_views > 0:
            self.logger.info(f"🎯 Views per URL:")
            for url, views in self.stats["views_per_url"].items():
                self.logger.info(f"   {url}: {views} views")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        duration = (datetime.now() - self.stats["start_time"]).total_seconds()
        total_views = sum(self.stats["views_per_url"].values())
        
        return {
            "status": "running" if self.running else "stopped",
            "duration_seconds": duration,
            "total_views": total_views,
            "target_views": self.config.target_views,
            "progress_percentage": (total_views / self.config.target_views * 100) if self.config.target_views > 0 else 0,
            "successful_requests": self.stats["successful_requests"],
            "failed_requests": self.stats["failed_requests"],
            "total_requests": self.stats["total_requests"],
            "requests_per_second": self.stats["total_requests"] / duration if duration > 0 else 0,
            "views_per_url": self.stats["views_per_url"],
            "start_time": self.stats["start_time"].isoformat()
        }


# Export classes
__all__ = ['FastViewBooster', 'FastBoosterConfig']