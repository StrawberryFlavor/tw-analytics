"""Data source manager for intelligent source switching and management."""

import logging
from typing import List, Dict, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from ...core.interfaces import DataSourceManagerInterface, DataSourceInterface, TweetData, UserData
from ...core.exceptions import DataSourceError, DataSourceUnavailableError


class DataSourceManager(DataSourceManagerInterface):
    """Intelligent data source manager with fallback and optimization."""
    
    def __init__(self, sources: Optional[List[DataSourceInterface]] = None):
        """
        Initialize data source manager with injected sources.
        
        Args:
            sources: List of data sources to use (injected dependency)
        """
        self.logger = logging.getLogger(__name__)
        self.sources: List[DataSourceInterface] = sources or []
        
        # Performance tracking
        self._source_performance = {}
        self._fallback_counts = {}
        
        # Initialize performance tracking for each source
        for source in self.sources:
            self._source_performance[source.name] = {
                'success_count': 0,
                'error_count': 0,
                'avg_response_time': 0
            }
            self._fallback_counts[source.name] = 0
            
        self.logger.info(f"DataSourceManager initialized with {len(self.sources)} sources")
        if not self.sources:
            self.logger.error("No data sources available!")
    
    async def get_comprehensive_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive tweet data using the best available source.
        Priority: Playwright > TwitterAPI (if it supports comprehensive data)
        """
        available_sources = self.get_available_sources()
        
        # 如果没有可用的数据源，尝试重置并重新检查
        if not available_sources:
            self.logger.warning("没有可用的数据源，尝试重置所有数据源健康状态")
            # 先调试当前状态
            self.debug_source_availability()
            
            self.reset_all_sources()
            available_sources = self.get_available_sources()
            
            if not available_sources:
                self.logger.error("重置后仍然没有可用的数据源")
                # 再次调试
                self.debug_source_availability()
                return None
            else:
                self.logger.info(f"重置后可用数据源: {[s.name for s in available_sources]}")
        
        for source in available_sources:
            try:
                # Check if source supports comprehensive data extraction
                if hasattr(source, 'get_comprehensive_data'):
                    self.logger.info(f"Attempting comprehensive data extraction with {source.name}")
                    result = await source.get_comprehensive_data(tweet_url)
                    if result:
                        self._record_success(source.name)
                        return result
                    
            except Exception as e:
                self.logger.warning(f"Comprehensive data extraction failed with {source.name}: {e}")
                self._record_failure(source.name)
                continue
        
        # No source could provide comprehensive data
        self.logger.error(f"All sources failed to provide comprehensive data for {tweet_url}")
        return None
    
    def get_available_sources(self) -> List[DataSourceInterface]:
        """Get list of currently available sources."""
        available = []
        for source in self.sources:
            is_available = source.is_available()
            self.logger.debug(f"数据源 {source.name} 可用性: {is_available}")
            if is_available:
                available.append(source)
            else:
                # 记录不可用的原因
                status = source.get_health_status()
                self.logger.debug(f"数据源 {source.name} 不可用，状态: {status}")
        
        self.logger.info(f"可用数据源: {[s.name for s in available]}, 总数据源: {[s.name for s in self.sources]}")
        return available
    
    def get_primary_source(self) -> Optional[DataSourceInterface]:
        """Get the primary (highest priority available) source."""
        available = self.get_available_sources()
        return available[0] if available else None
    
    async def get_tweet_data(self, tweet_id: str) -> TweetData:
        """
        Get tweet data with intelligent source selection and fallback.
        
        Args:
            tweet_id: Tweet ID or URL
            
        Returns:
            TweetData object
            
        Raises:
            DataSourceUnavailableError: If no sources are available
            DataSourceError: If all sources fail
        """
        available_sources = self.get_available_sources()
        
        if not available_sources:
            raise DataSourceUnavailableError("all", "No data sources available")
        
        last_error = None
        
        for source in available_sources:
            try:
                self.logger.info(f"Attempting to get tweet {tweet_id} from {source.name}")
                
                result = await source.get_tweet_data(tweet_id)
                
                # Track successful usage
                self._record_success(source.name)
                
                self.logger.info(f"Successfully retrieved tweet {tweet_id} from {source.name}")
                return result
                
            except Exception as e:
                # 检查是否是风控异常（检查异常名称和属性）
                if (hasattr(e, 'wait_time') and 
                    type(e).__name__ == 'RateLimitDetectedError'):
                    self.logger.warning(f"🚨 {source.name} 检测到风控，暂时跳过: {e}")
                    # 不记录为失败，因为这不是数据源的问题
                    last_error = e
                    continue
                
                last_error = e
                self._record_failure(source.name)
                self.logger.warning(f"Failed to get tweet {tweet_id} from {source.name}: {e}")
                continue
        
        # All sources failed
        raise DataSourceError(f"All data sources failed to get tweet {tweet_id}. Last error: {last_error}")
    
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List[TweetData]:
        """
        Batch get tweet data with intelligent distribution across sources.
        
        Args:
            tweet_ids: List of tweet IDs
            
        Returns:
            List of TweetData objects (may be partial if some tweets fail)
        """
        if not tweet_ids:
            return []
        
        available_sources = self.get_available_sources()
        
        if not available_sources:
            raise DataSourceUnavailableError("all", "No data sources available")
        
        # Try batch operation on primary source first
        primary_source = available_sources[0]
        
        try:
            self.logger.info(f"Attempting batch get {len(tweet_ids)} tweets from {primary_source.name}")
            
            results = await primary_source.batch_get_tweet_data(tweet_ids)
            
            if results:
                self._record_success(primary_source.name)
                self.logger.info(f"Successfully batch retrieved {len(results)} tweets from {primary_source.name}")
                return results
                
        except Exception as e:
            self.logger.warning(f"Batch operation failed on {primary_source.name}: {e}")
            self._record_failure(primary_source.name)
        
        # Fallback to individual requests across available sources
        self.logger.info("Falling back to individual requests across sources")
        return await self._fallback_batch_get(tweet_ids, available_sources)
    
    async def _fallback_batch_get(self, tweet_ids: List[str], sources: List[DataSourceInterface]) -> List[TweetData]:
        """Fallback batch get using individual requests distributed across sources."""
        results = []
        failed_ids = []
        
        # Distribute requests across available sources
        source_queues = {source.name: [] for source in sources}
        
        for i, tweet_id in enumerate(tweet_ids):
            source = sources[i % len(sources)]
            source_queues[source.name].append(tweet_id)
        
        # Process each source's queue
        tasks = []
        for source in sources:
            if source_queues[source.name]:
                task = self._process_source_queue(source, source_queues[source.name])
                tasks.append(task)
        
        # Wait for all tasks to complete
        if tasks:
            queue_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for queue_result in queue_results:
                if isinstance(queue_result, Exception):
                    self.logger.error(f"Queue processing error: {queue_result}")
                    continue
                
                successful, failed = queue_result
                results.extend(successful)
                failed_ids.extend(failed)
        
        self.logger.info(f"Fallback batch completed: {len(results)} successful, {len(failed_ids)} failed")
        return results
    
    async def _process_source_queue(self, source: DataSourceInterface, tweet_ids: List[str]) -> tuple:
        """Process a queue of tweet IDs for a specific source."""
        successful = []
        failed = []
        
        for tweet_id in tweet_ids:
            try:
                if not source.is_available():
                    failed.append(tweet_id)
                    continue
                
                result = await source.get_tweet_data(tweet_id)
                successful.append(result)
                self._record_success(source.name)
                
            except Exception as e:
                self.logger.warning(f"Failed to get tweet {tweet_id} from {source.name}: {e}")
                failed.append(tweet_id)
                self._record_failure(source.name)
        
        return successful, failed
    
    async def get_user_data(self, username: str) -> UserData:
        """Get user data with source fallback."""
        available_sources = self.get_available_sources()
        
        if not available_sources:
            raise DataSourceUnavailableError("all", "No data sources available")
        
        last_error = None
        
        for source in available_sources:
            try:
                self.logger.info(f"Attempting to get user @{username} from {source.name}")
                
                result = await source.get_user_data(username)
                
                self._record_success(source.name)
                self.logger.info(f"Successfully retrieved user @{username} from {source.name}")
                return result
                
            except Exception as e:
                last_error = e
                self._record_failure(source.name)
                self.logger.warning(f"Failed to get user @{username} from {source.name}: {e}")
                continue
        
        raise DataSourceError(f"All data sources failed to get user @{username}. Last error: {last_error}")
    
    async def get_user_tweets(self, username: str, max_results: int = 10) -> List[TweetData]:
        """Get user tweets with source fallback."""
        available_sources = self.get_available_sources()
        
        if not available_sources:
            raise DataSourceUnavailableError("all", "No data sources available")
        
        last_error = None
        
        for source in available_sources:
            try:
                self.logger.info(f"Attempting to get tweets for @{username} from {source.name}")
                
                results = await source.get_user_tweets(username, max_results)
                
                self._record_success(source.name)
                self.logger.info(f"Successfully retrieved {len(results)} tweets for @{username} from {source.name}")
                return results
                
            except Exception as e:
                last_error = e
                self._record_failure(source.name)
                self.logger.warning(f"Failed to get tweets for @{username} from {source.name}: {e}")
                continue
        
        # Return empty list if all sources fail for user tweets
        self.logger.warning(f"All sources failed to get tweets for @{username}")
        return []
    
    async def search_tweets(self, query: str, max_results: int = 10) -> List[TweetData]:
        """Search tweets with source fallback."""
        available_sources = self.get_available_sources()
        
        if not available_sources:
            raise DataSourceUnavailableError("all", "No data sources available")
        
        last_error = None
        
        for source in available_sources:
            try:
                self.logger.info(f"Attempting to search tweets '{query}' from {source.name}")
                
                results = await source.search_tweets(query, max_results)
                
                self._record_success(source.name)
                self.logger.info(f"Successfully searched tweets '{query}' from {source.name}, found {len(results)} results")
                return results
                
            except Exception as e:
                last_error = e
                self._record_failure(source.name)
                self.logger.warning(f"Failed to search tweets '{query}' from {source.name}: {e}")
                continue
        
        # Return empty list if all sources fail for search
        self.logger.warning(f"All sources failed to search tweets '{query}'")
        return []
    
    def _record_success(self, source_name: str):
        """Record successful operation for performance tracking."""
        if source_name not in self._source_performance:
            self._source_performance[source_name] = {
                'success_count': 0, 
                'error_count': 0,
                'avg_response_time': 0
            }
        
        self._source_performance[source_name]['success_count'] += 1
    
    def _record_failure(self, source_name: str):
        """Record failed operation for performance tracking."""
        if source_name not in self._source_performance:
            self._source_performance[source_name] = {
                'success_count': 0, 
                'error_count': 0,
                'avg_response_time': 0
            }
        
        self._source_performance[source_name]['error_count'] += 1
        
        if source_name not in self._fallback_counts:
            self._fallback_counts[source_name] = 0
        
        self._fallback_counts[source_name] += 1
        
        # 如果某个数据源失败太多次，考虑临时重置其健康状态
        error_count = self._source_performance[source_name]['error_count']
        if error_count > 0 and error_count % 10 == 0:  # 每10次失败重置一次
            self.logger.warning(f"数据源 {source_name} 已失败 {error_count} 次，尝试重置其健康状态")
            for source in self.sources:
                if source.name == source_name:
                    source.reset_health()
                    break
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed status of all data sources."""
        sources_status = []
        available_count = 0
        
        for source in self.sources:
            source_status = source.get_health_status()
            is_available = source.is_available()
            source_status['is_available'] = is_available
            
            if is_available:
                available_count += 1
            
            sources_status.append(source_status)
        
        status = {
            'total_sources': len(self.sources),
            'available_sources': available_count,
            'sources': sources_status,
            'performance': self._source_performance,
            'fallback_counts': self._fallback_counts
        }
        
        return status
    
    def debug_source_availability(self):
        """调试数据源可用性问题"""
        self.logger.info(f"=== 数据源可用性调试 ===")
        self.logger.info(f"总数据源数量: {len(self.sources)}")
        
        for i, source in enumerate(self.sources, 1):
            status = source.get_health_status()
            is_available = source.is_available()
            
            self.logger.info(f"数据源 {i}: {source.name}")
            self.logger.info(f"  - 可用性: {is_available}")
            self.logger.info(f"  - 健康状态: {status}")
            
            # 对于PlaywrightPooledSource，检查额外信息
            if hasattr(source, '_pool_initialized'):
                self.logger.info(f"  - 池初始化状态: {source._pool_initialized}")
            if hasattr(source, '_initialization_failed'):
                self.logger.info(f"  - 初始化失败标记: {getattr(source, '_initialization_failed', False)}")
        
        available_sources = self.get_available_sources()
        self.logger.info(f"当前可用数据源: {[s.name for s in available_sources]}")
        self.logger.info(f"=== 调试结束 ===")
    
    def reset_all_sources(self):
        """Reset health status of all sources."""
        for source in self.sources:
            source.reset_health()
        
        # Clear performance tracking
        self._source_performance.clear()
        self._fallback_counts.clear()
        
        self.logger.info("All data sources reset successfully")