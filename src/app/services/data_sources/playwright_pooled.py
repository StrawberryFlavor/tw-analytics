"""
使用浏览器池的增强Playwright数据源
提供高性能并发数据提取能力
"""

import asyncio
import logging
import os
import time
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .base import BaseDataSource
from .extractors import TweetDataExtractor
from .extractors.rate_limit_detector import rate_limit_detector
from ...core.interfaces import TweetData, UserData
from ...core.exceptions import DataSourceError, NotFoundError
from ..browser_pool import BrowserPool


class PlaywrightPooledSource(BaseDataSource):
    """
    使用浏览器池的增强Playwright数据源
    
    特性:
    - 浏览器实例池化，避免重复启动开销
    - 并发请求处理
    - 智能请求去重
    - 高效的批量处理
    - 自动故障恢复
    """
    
    def __init__(self, 
                 pool_min_size: int = 2,
                 pool_max_size: int = 6,
                 max_concurrent_requests: int = None):
        """
        初始化池化数据源 (简化版配置)
        
        Args:
            pool_min_size: 浏览器池最小大小
            pool_max_size: 浏览器池最大大小  
            max_concurrent_requests: 最大并发请求数（默认为池大小）
        """
        super().__init__("PlaywrightPooled")
        
        # 浏览器池配置
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.max_concurrent_requests = max_concurrent_requests or pool_max_size
        
        # 浏览器池实例
        self._browser_pool: Optional[BrowserPool] = None
        self._pool_initialized = False
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        self._request_queue = asyncio.Queue()
        self._active_requests: Set[str] = set()  # 防重复请求
        
        # 性能统计
        self.last_request_time = 0
        self.request_interval = 1.0  # 请求间隔（池化后可以更短）
        self._max_retries = 2
        self._retry_delay = 2.0
        
        self.logger.info(f"初始化池化数据源，池大小: {pool_min_size}-{pool_max_size}, 并发: {self.max_concurrent_requests}")
    
    def is_available(self) -> bool:
        """
        检查Playwright数据源是否可用
        
        对于Playwright数据源，即使初始化失败也应该保持可用状态以便重试
        除非健康状态被明确标记为False（例如由于过多连续错误）
        """
        from datetime import datetime
        
        # 检查是否在速率限制期间
        if self._rate_limit_reset and datetime.now() < self._rate_limit_reset:
            return False
        
        # 对于Playwright数据源，保持更宽松的可用性检查
        # 允许初始化失败后的重试
        return self._healthy
    
    async def initialize(self):
        """初始化浏览器池（应在服务启动时调用）"""
        if not self._pool_initialized:
            self.logger.info("正在预初始化浏览器池...")
            await self._ensure_pool_initialized()
            self.logger.info("浏览器池预初始化完成")
    
    async def _ensure_pool_initialized(self):
        """确保浏览器池已初始化（跨进程安全）"""
        process_id = os.getpid()
        
        # 检查是否需要重新初始化
        if (self._pool_initialized and 
            hasattr(self, '_init_pid') and 
            self._init_pid == process_id and 
            self._browser_pool):
            self.logger.debug(f"浏览器池已初始化 (PID: {process_id})")
            return
        
        # 需要初始化的情况处理
        if not self._pool_initialized:
            self.logger.debug("浏览器池未初始化")
        elif not hasattr(self, '_init_pid') or self._init_pid != process_id:
            self.logger.info(f"进程fork检测到，重新初始化浏览器池 (PID: {getattr(self, '_init_pid', 'None')} -> {process_id})")
        elif not self._browser_pool:
            self.logger.debug("浏览器池实例不存在，需要重新创建")
        
        try:
            self.logger.info(f"初始化浏览器池 (PID: {process_id})")
            self._browser_pool = BrowserPool(
                min_size=self.pool_min_size,
                max_size=self.pool_max_size
            )
            
            # 检查是否启用账户管理
            from ...config import Config
            if Config.ACCOUNT_MANAGEMENT_ENABLED:
                await self._browser_pool.initialize_with_account_manager()
                self.logger.info("浏览器池已启用账户管理功能")
            else:
                await self._browser_pool.initialize()
                self.logger.info("浏览器池未启用账户管理功能")
            
            self._pool_initialized = True
            self._init_pid = process_id
            self.logger.info(f"浏览器池初始化完成，池大小: {self.pool_min_size}-{self.pool_max_size}")
        except Exception as e:
            self.logger.error(f"浏览器池初始化失败: {e}")
            self._pool_initialized = False
            self._browser_pool = None
            raise
    
    async def _rate_limit(self):
        """轻量级限流（池化后限流可以更宽松）"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.request_interval:
            sleep_time = self.request_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def get_comprehensive_data(self, tweet_url: str) -> Dict[str, Any]:
        """
        获取推文页面的综合数据
        
        Args:
            tweet_url: 推文URL
            
        Returns:
            包含所有提取数据的字典
        """
        # 去重检查
        if tweet_url in self._active_requests:
            self.logger.debug(f"请求去重: {tweet_url}")
            # 简单等待策略，实际应用中可以实现更复杂的等待/共享机制
            await asyncio.sleep(0.5)
            return await self.get_comprehensive_data(tweet_url)
        
        tweet_id = self._extract_tweet_id_from_url(tweet_url)
        
        async with self._semaphore:  # 并发控制
            self.logger.info(f"开始池化提取: {tweet_url}")
            
            self._active_requests.add(tweet_url)
            try:
                await self._ensure_pool_initialized()
                data = await self._extract_comprehensive_data_pooled(tweet_url, tweet_id)
                self.handle_success()
                return data
            except Exception as e:
                error = DataSourceError(f"池化提取失败: {str(e)}")
                self.handle_error(error)
                raise error
            finally:
                self._active_requests.discard(tweet_url)
    
    async def _extract_comprehensive_data_pooled(self, url: str, target_tweet_id: str = None) -> Dict[str, Any]:
        """使用浏览器池进行数据提取"""
        start_time = time.time()
        instance = None
        context = None
        page = None
        
        try:
            await self._rate_limit()
            
            # 从池中获取浏览器实例
            self.logger.info(f"正在从浏览器池获取实例...")
            
            # 先检查池状态
            pool_status = await self._browser_pool.get_pool_status()
            self.logger.info(f"浏览器池状态: 实例数={pool_status.get('total_instances', 0)}, "
                           f"可用数={pool_status.get('available_instances', 0)}")
            
            # 增加超时时间到30秒
            instance, context, page = await self._browser_pool.acquire_instance(timeout=30.0)
            self.logger.info(f"成功获取浏览器实例: {instance.instance_id if instance else 'None'}")
            
            # 认证由浏览器实例内部处理，无需额外cookie加载
            self.logger.debug("使用账户管理系统统一认证")
            
            # 添加随机延迟，模拟人类行为
            from ..browser_pool.anti_detection import AntiDetectionManager
            anti_detection = AntiDetectionManager()
            
            if anti_detection.should_add_human_delay():
                delay = anti_detection.get_random_delay(0.5, 2.0)
                self.logger.debug(f"添加人类行为延迟: {delay:.2f}s")
                await asyncio.sleep(delay)
            
            # 导航到页面
            self.logger.info(f"正在导航到页面: {url}")
            response = await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            self.logger.info(f"页面导航完成，状态码: {response.status if response else 'None'}")
            
            if response and response.status >= 400:
                raise DataSourceError(f"HTTP错误: {response.status}")
            
            # 验证页面
            current_url = page.url
            if not any(domain in current_url for domain in ['x.com', 'twitter.com']):
                raise DataSourceError(f"导航失败，当前URL: {current_url}")
            
            # 使用提取器，添加超时保护
            extractor = TweetDataExtractor(page)
            self.logger.info("开始数据提取")
            
            try:
                # 从环境变量获取超时时间，默认30秒
                import os
                from dotenv import load_dotenv
                load_dotenv()  # 确保加载.env文件
                timeout = float(os.getenv('PLAYWRIGHT_EXTRACTION_TIMEOUT', '30.0'))
                
                comprehensive_data = await asyncio.wait_for(
                    extractor.extract_all_data(target_tweet_id),
                    timeout=timeout
                )
                self.logger.info("数据提取完成")
            except asyncio.TimeoutError:
                # 超时可能是风控引起的，使用风控检测器判断
                timeout_error = f"数据提取超时（{timeout}秒）"
                if rate_limit_detector.is_rate_limited(timeout_error):
                    self.logger.warning(f"检测到可能的风控引起的超时: {url}")
                    try:
                        # 使用风控检测器的安全等待方法
                        await rate_limit_detector.safe_wait_for_selector(
                            page, '[data-testid="tweet"]', timeout=5000
                        )
                        # 如果成功了，重试数据提取
                        comprehensive_data = await asyncio.wait_for(
                            extractor.extract_all_data(target_tweet_id),
                            timeout=timeout
                        )
                        self.logger.info("风控处理后数据提取完成")
                    except Exception as rate_limit_error:
                        # 如果是风控异常，让它传播到上层
                        if (hasattr(rate_limit_error, 'wait_time') and 
                            type(rate_limit_error).__name__ == 'RateLimitDetectedError'):
                            raise rate_limit_error
                        else:
                            raise DataSourceError(timeout_error)
                else:
                    raise DataSourceError(timeout_error)
            
            # 添加提取元数据
            metadata = {
                'source': 'PlaywrightPooled',
                'instance_id': instance.instance_id if instance else 'unknown',
                'page_load_time': f"{(time.time() - start_time):.2f}s",
                'final_url': current_url,
                'pool_size': len(self._browser_pool.instances) if self._browser_pool else 0
            }
            
            # 添加浏览器实例信息（包含账户管理信息）
            if instance:
                browser_info = {
                    'instance_id': instance.instance_id,
                    'current_account': instance.current_account.username if instance.current_account else None,
                    'account_usage_count': instance.account_usage_count,
                    'account_switch_threshold': instance.account_switch_threshold,
                    'using_env_cookie': instance.using_env_cookie
                }
                comprehensive_data['browser_info'] = browser_info
                self.logger.debug(f"账户信息: {browser_info}")
            
            comprehensive_data['extraction_metadata'].update(metadata)
            
            tweet_count = (
                (1 if comprehensive_data.get('primary_tweet') else 0) +
                len(comprehensive_data.get('thread_tweets', [])) +
                len(comprehensive_data.get('related_tweets', []))
            )
            
            self.logger.info(f"池化提取完成: {tweet_count} 条推文, 用时 {time.time() - start_time:.2f}s")
            return comprehensive_data
            
        except Exception as e:
            # 检查是否是风控异常
            if (hasattr(e, 'wait_time') and 
                type(e).__name__ == 'RateLimitDetectedError'):
                self.logger.warning(f"池化提取检测到风控: {e}")
                # 风控异常需要传播到上层处理，但不算实例失败
                if instance:
                    await self._browser_pool.release_instance(instance, success=True)
                    instance = None
                raise  # 传播风控异常
            else:
                self.logger.error(f"池化提取失败: {e}")
                if instance:
                    await self._browser_pool.release_instance(instance, success=False)
                    instance = None  # 避免重复释放
                raise
        finally:
            # 释放浏览器实例
            if instance:
                await self._browser_pool.release_instance(instance, success=True)
    
    async def get_tweet_data(self, tweet_id: str) -> TweetData:
        """获取单条推文数据"""
        tweet_id = self._extract_tweet_id(tweet_id)
        
        if not self._validate_tweet_id(tweet_id):
            raise ValueError(f"无效的推文ID: {tweet_id}")
        
        tweet_url = f"https://x.com/i/web/status/{tweet_id}"
        comprehensive_data = await self.get_comprehensive_data(tweet_url)
        
        # 提取主推文
        primary_tweet = comprehensive_data.get('primary_tweet')
        if not primary_tweet:
            raise NotFoundError(f"推文 {tweet_id} 未找到")
        
        return self._convert_to_tweet_data(primary_tweet, tweet_id)
    
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List[TweetData]:
        """
        并发批量获取推文数据
        
        这是池化数据源的主要优势 - 可以并行处理多个请求
        """
        if not tweet_ids:
            return []
        
        self.logger.info(f"开始并发批量处理 {len(tweet_ids)} 条推文")
        
        # 创建并发任务
        tasks = []
        for tweet_id in tweet_ids:
            cleaned_id = self._extract_tweet_id(tweet_id)
            if self._validate_tweet_id(cleaned_id):
                task = self._get_single_tweet_with_retry(cleaned_id)
                tasks.append(task)
        
        if not tasks:
            return []
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤结果
        successful_results = []
        failed_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                self.logger.warning(f"批量处理中的失败: {result}")
                failed_count += 1
            elif result:
                successful_results.append(result)
        
        self.logger.info(f"并发批量处理完成: {len(successful_results)} 成功, {failed_count} 失败")
        return successful_results
    
    async def _get_single_tweet_with_retry(self, tweet_id: str) -> Optional[TweetData]:
        """带重试的单推文获取"""
        for attempt in range(self._max_retries + 1):
            try:
                return await self.get_tweet_data(tweet_id)
            except Exception as e:
                if attempt < self._max_retries:
                    self.logger.warning(f"推文 {tweet_id} 获取失败 (尝试 {attempt + 1}/{self._max_retries + 1}): {e}")
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
                else:
                    self.logger.error(f"推文 {tweet_id} 最终获取失败: {e}")
                    return None
    
    async def get_user_tweets(self, username: str, max_results: int = 10) -> List[TweetData]:
        """获取用户推文"""
        username = username.lstrip('@')
        
        if not self._validate_username(username):
            raise ValueError(f"无效的用户名: {username}")
        
        profile_url = f"https://x.com/{username}"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(profile_url)
            
            # 提取该用户的推文
            user_tweets = []
            
            # 检查主推文
            primary_tweet = comprehensive_data.get('primary_tweet')
            if (primary_tweet and 
                primary_tweet.get('author', {}).get('username') == username):
                user_tweets.append(self._convert_to_tweet_data(primary_tweet))
            
            # 检查线程推文
            for tweet in comprehensive_data.get('thread_tweets', []):
                if tweet.get('author', {}).get('username') == username:
                    user_tweets.append(self._convert_to_tweet_data(tweet))
            
            # 检查相关推文
            for tweet in comprehensive_data.get('related_tweets', []):
                if tweet.get('author', {}).get('username') == username:
                    user_tweets.append(self._convert_to_tweet_data(tweet))
            
            return user_tweets[:max_results]
            
        except Exception as e:
            self.logger.error(f"获取用户 @{username} 推文失败: {e}")
            return []
    
    async def get_user_data(self, username: str) -> UserData:
        """获取用户数据"""
        username = username.lstrip('@')
        
        if not self._validate_username(username):
            raise ValueError(f"无效的用户名: {username}")
        
        profile_url = f"https://x.com/{username}"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(profile_url)
            
            # 从推文中提取用户信息
            user_info = None
            for tweet_source in ['primary_tweet', 'thread_tweets', 'related_tweets']:
                if tweet_source == 'primary_tweet':
                    tweet = comprehensive_data.get(tweet_source)
                    if tweet and tweet.get('author', {}).get('username') == username:
                        user_info = tweet['author']
                        break
                else:
                    tweets = comprehensive_data.get(tweet_source, [])
                    for tweet in tweets:
                        if tweet.get('author', {}).get('username') == username:
                            user_info = tweet['author']
                            break
                    if user_info:
                        break
            
            if not user_info:
                raise NotFoundError(f"用户 @{username} 未找到")
            
            return UserData(
                user_id=user_info.get('username', username),
                username=user_info.get('username', username),
                name=user_info.get('display_name', username),
                description=None,
                public_metrics={
                    'followers_count': 0,
                    'following_count': 0,
                    'tweet_count': 0,
                    'listed_count': 0
                },
                profile_image_url=user_info.get('avatar_url'),
                verified=user_info.get('is_verified', False)
            )
            
        except Exception as e:
            error = DataSourceError(f"获取用户 @{username} 数据失败: {str(e)}")
            self.handle_error(error)
            raise error
    
    async def search_tweets(self, query: str, max_results: int = 10) -> List[TweetData]:
        """搜索推文"""
        if not query or not query.strip():
            raise ValueError("搜索查询不能为空")
        
        search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(search_url)
            
            # 提取搜索结果
            search_results = []
            
            for tweet_source in ['primary_tweet', 'thread_tweets', 'related_tweets']:
                if tweet_source == 'primary_tweet':
                    tweet = comprehensive_data.get(tweet_source)
                    if tweet:
                        search_results.append(self._convert_to_tweet_data(tweet))
                else:
                    tweets = comprehensive_data.get(tweet_source, [])
                    for tweet in tweets:
                        search_results.append(self._convert_to_tweet_data(tweet))
            
            return search_results[:max_results]
            
        except Exception as e:
            self.logger.error(f"搜索推文失败 '{query}': {e}")
            return []
    
    async def get_pool_status(self) -> Dict[str, Any]:
        """获取浏览器池状态"""
        if not self._browser_pool or not self._pool_initialized:
            return {
                'initialized': False,
                'error': '浏览器池未初始化'
            }
        
        return await self._browser_pool.get_pool_status()
    
    def _convert_to_tweet_data(self, tweet_dict: Dict[str, Any], fallback_id: str = None) -> TweetData:
        """转换推文数据格式"""
        author = tweet_dict.get('author', {})
        metrics = tweet_dict.get('metrics', {})
        
        return TweetData(
            tweet_id=tweet_dict.get('tweet_id') or fallback_id or 'unknown',
            text=tweet_dict.get('text', ''),
            author_username=author.get('username', 'unknown'),
            author_name=author.get('display_name', 'Unknown'),
            created_at=tweet_dict.get('timestamp') or datetime.now().isoformat(),
            public_metrics={
                'retweet_count': metrics.get('retweets', 0),
                'like_count': metrics.get('likes', 0),
                'reply_count': metrics.get('replies', 0),
                'quote_count': metrics.get('quotes', 0)
            },
            view_count=metrics.get('views'),
            url=f"https://twitter.com/{author.get('username', 'unknown')}/status/{tweet_dict.get('tweet_id', 'unknown')}",
            lang=tweet_dict.get('language')
        )
    
    def _extract_tweet_id_from_url(self, url: str) -> Optional[str]:
        """从URL提取推文ID"""
        import re
        match = re.search(r'/status/(\d+)', url)
        return match.group(1) if match else None
    
    async def cleanup(self):
        """清理资源"""
        if self._browser_pool:
            await self._browser_pool.dispose()
            self._browser_pool = None
            self._pool_initialized = False
        
        self.logger.info("池化数据源已清理")
    
    def __del__(self):
        """析构时确保资源清理"""
        if self._browser_pool and self._pool_initialized:
            # 注意：在析构函数中不能使用async/await
            self.logger.warning("检测到未清理的浏览器池，请调用cleanup()方法")
