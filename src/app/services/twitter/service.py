"""Twitter business service implementation."""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ...core.interfaces import (
    TwitterServiceInterface, 
    TweetData, 
    UserData,
    DataSourceManagerInterface,
    AsyncRunnerInterface
)
from ..utils import extract_tweet_id, validate_tweet_id, validate_username


class TwitterService(TwitterServiceInterface):
    """Main Twitter business service implementation."""
    
    def __init__(self, 
                 data_manager: DataSourceManagerInterface,
                 async_runner: AsyncRunnerInterface):
        """
        Initialize Twitter service with injected dependencies.
        
        Args:
            data_manager: Data source manager for fetching data
            async_runner: Async runner for executing async operations in sync context
        """
        self.logger = logging.getLogger(__name__)
        self._data_manager = data_manager
        self._async_runner = async_runner
    
    @property
    def data_manager(self) -> DataSourceManagerInterface:
        """Get data source manager instance."""
        return self._data_manager
    
    def _run_async(self, coro, timeout: Optional[float] = None):
        """Run async coroutine in sync context."""
        return self._async_runner.run(coro, timeout=timeout)
    
    async def get_tweet_views(self, tweet_id: str) -> Optional[int]:
        """Get tweet view count."""
        tweet_id = extract_tweet_id(tweet_id)
        
        if not validate_tweet_id(tweet_id):
            raise ValueError(f"Invalid tweet ID: {tweet_id}")
        
        try:
            tweet_data = await self.data_manager.get_tweet_data(tweet_id)
            return tweet_data.view_count
        except Exception as e:
            self.logger.error(f"Failed to get tweet views for {tweet_id}: {e}")
            raise
    
    def get_tweet_views_sync(self, tweet_id: str) -> Optional[int]:
        """Synchronous wrapper for get_tweet_views."""
        return self._run_async(self.get_tweet_views(tweet_id))
    
    async def get_tweet_metrics(self, tweet_id: str) -> TweetData:
        """Get complete tweet metrics."""
        tweet_id = extract_tweet_id(tweet_id)
        
        if not validate_tweet_id(tweet_id):
            raise ValueError(f"Invalid tweet ID: {tweet_id}")
        
        try:
            tweet_data = await self.data_manager.get_tweet_data(tweet_id)
            return tweet_data
        except Exception as e:
            self.logger.error(f"Failed to get tweet metrics for {tweet_id}: {e}")
            raise
    
    def get_tweet_metrics_sync(self, tweet_id: str) -> TweetData:
        """Synchronous wrapper for get_tweet_metrics."""
        return self._run_async(self.get_tweet_metrics(tweet_id))
    
    async def get_tweet_by_url(self, tweet_url: str) -> TweetData:
        """
        Get tweet data by URL.
        
        Args:
            tweet_url: Tweet URL (e.g., https://twitter.com/user/status/123456789)
            
        Returns:
            TweetData object with all available metrics
        """
        return await self.get_tweet_metrics(tweet_url)
    
    def get_tweet_by_url_sync(self, tweet_url: str) -> TweetData:
        """Synchronous wrapper for get_tweet_by_url."""
        return self._run_async(self.get_tweet_by_url(tweet_url))
    
    async def batch_get_tweets_by_urls(self, tweet_urls: List[str]) -> List[TweetData]:
        """
        Batch get tweet data by URLs.
        
        Args:
            tweet_urls: List of tweet URLs
            
        Returns:
            List of TweetData objects
        """
        if not tweet_urls:
            return []
        
        # Extract tweet IDs from URLs
        tweet_ids = [extract_tweet_id(url) for url in tweet_urls]
        
        # Filter out invalid IDs
        valid_ids = [tid for tid in tweet_ids if validate_tweet_id(tid)]
        
        if not valid_ids:
            self.logger.warning("No valid tweet IDs found in provided URLs")
            return []
        
        try:
            tweets = await self.data_manager.batch_get_tweet_data(valid_ids)
            return tweets
        except Exception as e:
            self.logger.error(f"Failed to batch get tweets by URLs: {e}")
            raise
    
    def batch_get_tweets_by_urls_sync(self, tweet_urls: List[str]) -> List[TweetData]:
        """Synchronous wrapper for batch_get_tweets_by_urls."""
        return self._run_async(self.batch_get_tweets_by_urls(tweet_urls))
    
    async def get_comprehensive_tweet_data(self, tweet_url: str) -> Dict[str, Any]:
        """
        Get comprehensive data from a Twitter page including all visible content.
        This is more efficient for Playwright as it extracts everything in one page load.
        
        Args:
            tweet_url: Full Twitter URL
            
        Returns:
            Dictionary with comprehensive page data including:
            - primary_tweet: The main tweet
            - thread_tweets: Tweets in the same thread
            - related_tweets: Other tweets on the page
            - user_profile: User profile information
            - page_context: Page metadata
        """
        try:
            # Use data manager to get comprehensive data
            # The data manager will automatically select the best available source
            comprehensive_data = await self._data_manager.get_comprehensive_data(tweet_url)
            if comprehensive_data:
                self.logger.info(f"Retrieved comprehensive data for {tweet_url}")
                return comprehensive_data
            
            # Fallback strategy 1: Try regular data manager
            tweet_id = self._extract_tweet_id_from_url(tweet_url)
            if tweet_id:
                try:
                    tweet_data = await self.get_tweet_metrics(tweet_id)
                    self.logger.info(f"Using fallback extraction for {tweet_url}")
                    
                    return {
                        "primary_tweet": self._tweet_data_to_dict(tweet_data),
                        "thread_tweets": [],
                        "related_tweets": [],
                        "user_profile": {},
                        "page_context": {"extraction_method": "fallback_single_tweet"},
                        "extraction_metadata": {
                            "timestamp": datetime.now().isoformat(),
                            "source": "fallback",
                            "extraction_method": "single_tweet",
                            "note": "Comprehensive extraction failed, using single tweet fallback"
                        }
                    }
                except Exception as fallback_error:
                    self.logger.warning(f"Fallback extraction also failed: {fallback_error}")
            
            # Fallback strategy 2: Return minimal structure with error information
            return self._create_error_response(tweet_url, "All extraction methods failed")
                    
        except Exception as e:
            self.logger.error(f"Failed to get comprehensive data for {tweet_url}: {e}")
            return self._create_error_response(tweet_url, str(e))
    
    def get_comprehensive_tweet_data_sync(self, tweet_url: str) -> Dict[str, Any]:
        """Synchronous wrapper for get_comprehensive_tweet_data."""
        return self._run_async(self.get_comprehensive_tweet_data(tweet_url))
    
    def _extract_tweet_id_from_url(self, url: str) -> Optional[str]:
        """Extract tweet ID from Twitter URL."""
        import re
        match = re.search(r'/status/(\d+)', url)
        return match.group(1) if match else None
    
    def _tweet_data_to_dict(self, tweet_data: TweetData) -> Dict[str, Any]:
        """Convert TweetData to dictionary format for comprehensive response."""
        return {
            "tweet_id": tweet_data.tweet_id,
            "text": tweet_data.text,
            "author": {
                "username": tweet_data.author_username,
                "display_name": tweet_data.author_name
            },
            "timestamp": tweet_data.created_at,
            "metrics": {
                "views": tweet_data.view_count,
                "likes": tweet_data.public_metrics.get('like_count', 0),
                "retweets": tweet_data.public_metrics.get('retweet_count', 0),
                "replies": tweet_data.public_metrics.get('reply_count', 0),
                "quotes": tweet_data.public_metrics.get('quote_count', 0)
            },
            "language": tweet_data.lang,
            "url": tweet_data.url
        }
    
    def _create_error_response(self, tweet_url: str, error_message: str) -> Dict[str, Any]:
        """Create a comprehensive response structure for error cases."""
        return {
            "primary_tweet": None,
            "thread_tweets": [],
            "related_tweets": [],
            "user_profile": {},
            "page_context": {
                "page_type": "tweet",
                "is_logged_in": False,
                "language": "en",
                "theme": "light"
            },
            "extraction_metadata": {
                "timestamp": datetime.now().isoformat(),
                "source": "error",
                "extraction_method": "error",
                "page_url": tweet_url,
                "page_load_time": "0.00s",
                "final_url": tweet_url,
                "target_tweet_id": self._extract_tweet_id_from_url(tweet_url) or "unknown",
                "error": error_message,
                "note": "Extraction failed, returning empty structure"
            }
        }
    
    async def get_user_info(self, username: str) -> UserData:
        """Get user information."""
        username = username.lstrip('@')
        
        if not validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        try:
            user_data = await self.data_manager.get_user_data(username)
            return user_data
        except Exception as e:
            self.logger.error(f"Failed to get user info for @{username}: {e}")
            raise
    
    def get_user_info_sync(self, username: str) -> UserData:
        """Synchronous wrapper for get_user_info."""
        return self._run_async(self.get_user_info(username))
    
    async def get_user_recent_tweets_with_metrics(self, username: str, max_results: int = 10) -> List[TweetData]:
        """Get user's recent tweets with metrics."""
        username = username.lstrip('@')
        
        if not validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        try:
            tweets = await self.data_manager.get_user_tweets(username, max_results)
            return tweets
        except Exception as e:
            self.logger.error(f"Failed to get tweets for @{username}: {e}")
            raise
    
    def get_user_recent_tweets_with_metrics_sync(self, username: str, max_results: int = 10) -> List[TweetData]:
        """Synchronous wrapper for get_user_recent_tweets_with_metrics."""
        return self._run_async(self.get_user_recent_tweets_with_metrics(username, max_results))
    
    async def search_tweets(self, query: str, max_results: int = 10) -> List[TweetData]:
        """Search tweets."""
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")
        
        try:
            tweets = await self.data_manager.search_tweets(query.strip(), max_results)
            return tweets
        except Exception as e:
            self.logger.error(f"Failed to search tweets with query '{query}': {e}")
            raise
    
    def search_tweets_sync(self, query: str, max_results: int = 10) -> List[TweetData]:
        """Synchronous wrapper for search_tweets."""
        return self._run_async(self.search_tweets(query, max_results))
    
    async def get_tweet_engagement_rate(self, tweet_id: str) -> float:
        """Calculate tweet engagement rate."""
        tweet_id = extract_tweet_id(tweet_id)
        
        if not validate_tweet_id(tweet_id):
            raise ValueError(f"Invalid tweet ID: {tweet_id}")
        
        try:
            tweet_data = await self.data_manager.get_tweet_data(tweet_id)
            return tweet_data.engagement_rate
        except Exception as e:
            self.logger.error(f"Failed to get engagement rate for {tweet_id}: {e}")
            raise
    
    def get_tweet_engagement_rate_sync(self, tweet_id: str) -> float:
        """Synchronous wrapper for get_tweet_engagement_rate."""
        return self._run_async(self.get_tweet_engagement_rate(tweet_id))
    
    async def batch_get_tweet_views(self, tweet_ids: List[str]) -> Dict[str, Optional[int]]:
        """Batch get tweet view counts."""
        if not tweet_ids:
            return {}
        
        # Clean and validate tweet IDs
        clean_ids = []
        id_mapping = {}
        
        for original_id in tweet_ids:
            clean_id = extract_tweet_id(original_id)
            if validate_tweet_id(clean_id):
                clean_ids.append(clean_id)
                id_mapping[clean_id] = original_id
        
        if not clean_ids:
            return {}
        
        try:
            tweet_data_list = await self.data_manager.batch_get_tweet_data(clean_ids)
            
            results = {}
            
            # Initialize all requested IDs to None
            for original_id in tweet_ids:
                results[original_id] = None
            
            # Fill in successful results
            for tweet_data in tweet_data_list:
                original_id = id_mapping.get(tweet_data.tweet_id)
                if original_id:
                    results[original_id] = tweet_data.view_count
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to batch get tweet views: {e}")
            raise
    
    def batch_get_tweet_views_sync(self, tweet_ids: List[str]) -> Dict[str, Optional[int]]:
        """Synchronous wrapper for batch_get_tweet_views."""
        return self._run_async(self.batch_get_tweet_views(tweet_ids))
    
    def get_data_sources_status(self) -> Dict[str, Any]:
        """Get status of all data sources."""
        return self.data_manager.get_status()
    
    def reset_data_sources(self):
        """Reset all data sources."""
        self.data_manager.reset_all_sources()
        self.logger.info("All data sources reset")
    
    # Legacy method compatibility
    def get_tweet_by_id(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """Legacy method for backward compatibility."""
        try:
            tweet_data = self.get_tweet_metrics_sync(tweet_id)
            return {
                'tweet_id': tweet_data.tweet_id,
                'text': tweet_data.text,
                'author_username': tweet_data.author_username,
                'author_name': tweet_data.author_name,
                'created_at': tweet_data.created_at,
                'public_metrics': tweet_data.public_metrics,
                'view_count': tweet_data.view_count,
                'url': tweet_data.url,
                'lang': tweet_data.lang
            }
        except Exception:
            return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Legacy method for backward compatibility."""
        try:
            user_data = self.get_user_info_sync(username)
            return {
                'user_id': user_data.user_id,
                'username': user_data.username,
                'name': user_data.name,
                'description': user_data.description,
                'public_metrics': user_data.public_metrics,
                'profile_image_url': user_data.profile_image_url,
                'verified': user_data.verified,
                'created_at': user_data.created_at
            }
        except Exception:
            return None
    
    def get_user_recent_tweets(self, username: str, count: int = 10) -> List[Dict[str, Any]]:
        """Legacy method for backward compatibility."""
        try:
            tweets = self.get_user_recent_tweets_with_metrics_sync(username, count)
            return [
                {
                    'tweet_id': tweet.tweet_id,
                    'text': tweet.text,
                    'author_username': tweet.author_username,
                    'author_name': tweet.author_name,
                    'created_at': tweet.created_at,
                    'public_metrics': tweet.public_metrics,
                    'view_count': tweet.view_count,
                    'url': tweet.url,
                    'lang': tweet.lang
                }
                for tweet in tweets
            ]
        except Exception:
            return []