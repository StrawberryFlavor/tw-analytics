"""Enhanced Playwright data source with comprehensive data extraction."""

import asyncio
import os
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from playwright.async_api import async_playwright

from .base import BaseDataSource
from .extractors import TweetDataExtractor
from ...core.interfaces import TweetData, UserData
from ...core.exceptions import DataSourceError, NotFoundError
from ...core.path_manager import get_cookie_file_path
from ..cookie_manager import get_cookie_manager


class PlaywrightSource(BaseDataSource):
    """Enhanced Playwright browser automation data source with comprehensive extraction."""
    
    def __init__(self):
        super().__init__("Playwright")
        self.last_request_time = 0
        self.request_interval = 2.0  # Increased interval for comprehensive extraction
        self._cookie_file = get_cookie_file_path()
        self._max_retries = 2
        self._retry_delay = 3.0
        # Remove ineffective caching since browser is restarted each time
        # Real performance gain would require persistent browser instance
    
    async def _rate_limit(self):
        """Rate limiting for requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.request_interval:
            sleep_time = self.request_interval - time_since_last
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def get_comprehensive_data(self, tweet_url: str) -> Dict[str, Any]:
        """
        Get comprehensive data from a Twitter page including all visible tweets,
        thread context, user info, and page metadata.
        
        Args:
            tweet_url: Full Twitter URL
            
        Returns:
            Dictionary with comprehensive page data
        """
        # Extract tweet ID if possible
        tweet_id = self._extract_tweet_id_from_url(tweet_url)
        
        try:
            data = await self._extract_comprehensive_data(tweet_url, tweet_id)
            self.handle_success()
            return data
            
        except Exception as e:
            error = DataSourceError(f"Comprehensive extraction failed: {str(e)}")
            self.handle_error(error)
            raise error
    
    async def get_tweet_data(self, tweet_id: str) -> TweetData:
        """
        Get single tweet data - now uses comprehensive extraction and filters result.
        This is more efficient as we get all data in one page load.
        """
        tweet_id = self._extract_tweet_id(tweet_id)
        
        if not self._validate_tweet_id(tweet_id):
            raise ValueError(f"Invalid tweet ID: {tweet_id}")
        
        # Construct URL and use comprehensive extraction
        tweet_url = f"https://x.com/i/web/status/{tweet_id}"
        comprehensive_data = await self.get_comprehensive_data(tweet_url)
        
        # Extract the primary tweet
        primary_tweet = comprehensive_data.get('primary_tweet')
        if not primary_tweet:
            raise NotFoundError(f"Tweet {tweet_id} not found in page data")
        
        # Convert to TweetData format
        return self._convert_to_tweet_data(primary_tweet, tweet_id)
    
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List[TweetData]:
        """
        Enhanced batch processing that can extract multiple tweets from thread pages
        or individual pages efficiently.
        """
        if not tweet_ids:
            return []
        
        results = []
        processed_urls = set()
        
        for tweet_id in tweet_ids:
            tweet_id = self._extract_tweet_id(tweet_id)
            if not self._validate_tweet_id(tweet_id):
                continue
            
            tweet_url = f"https://x.com/i/web/status/{tweet_id}"
            
            # Skip if we already processed this URL (might get multiple tweets from same page)
            if tweet_url in processed_urls:
                continue
            
            try:
                comprehensive_data = await self.get_comprehensive_data(tweet_url)
                processed_urls.add(tweet_url)
                
                # Extract all tweets from this page that match our request
                page_tweets = self._extract_matching_tweets(comprehensive_data, tweet_ids)
                results.extend(page_tweets)
                
                # Short delay between pages
                await asyncio.sleep(1.0)
                
            except Exception as e:
                self.logger.warning(f"Failed to extract data for {tweet_id}: {e}")
                continue
        
        self.logger.info(f"Batch extraction complete: {len(results)} tweets from {len(processed_urls)} pages")
        return results
    
    async def get_user_tweets(self, username: str, max_results: int = 10) -> List[TweetData]:
        """Get user tweets from their profile page."""
        username = username.lstrip('@')
        
        if not self._validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        profile_url = f"https://x.com/{username}"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(profile_url)
            
            # Extract tweets from all categories
            user_tweets = []
            
            # Add primary tweet if it's from this user
            primary_tweet = comprehensive_data.get('primary_tweet')
            if (primary_tweet and 
                primary_tweet.get('author', {}).get('username') == username):
                user_tweets.append(self._convert_to_tweet_data(primary_tweet))
            
            # Add thread tweets
            for tweet in comprehensive_data.get('thread_tweets', []):
                if tweet.get('author', {}).get('username') == username:
                    user_tweets.append(self._convert_to_tweet_data(tweet))
            
            # Add related tweets from this user
            for tweet in comprehensive_data.get('related_tweets', []):
                if tweet.get('author', {}).get('username') == username:
                    user_tweets.append(self._convert_to_tweet_data(tweet))
            
            # Limit results
            return user_tweets[:max_results]
            
        except Exception as e:
            self.logger.error(f"Failed to get user tweets for @{username}: {e}")
            return []
    
    async def get_user_data(self, username: str) -> UserData:
        """Extract user data from comprehensive page extraction."""
        username = username.lstrip('@')
        
        if not self._validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        profile_url = f"https://x.com/{username}"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(profile_url)
            
            # Extract user info from any available tweet
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
                raise NotFoundError(f"User @{username} not found")
            
            # Convert to UserData format
            return UserData(
                user_id=user_info.get('username', username),  # We don't have numeric ID
                username=user_info.get('username', username),
                name=user_info.get('display_name', username),
                description=None,  # Not available from tweet extraction
                public_metrics={
                    'followers_count': 0,  # Not available
                    'following_count': 0,  # Not available
                    'tweet_count': 0,      # Not available
                    'listed_count': 0      # Not available
                },
                profile_image_url=user_info.get('avatar_url'),
                verified=user_info.get('is_verified', False)
            )
            
        except Exception as e:
            error = DataSourceError(f"Failed to get user data for @{username}: {str(e)}")
            self.handle_error(error)
            raise error
    
    async def search_tweets(self, query: str, max_results: int = 10) -> List[TweetData]:
        """Search tweets using Twitter search page."""
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")
        
        # Construct search URL
        search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query"
        
        try:
            comprehensive_data = await self.get_comprehensive_data(search_url)
            
            # Extract all tweets from search results
            search_results = []
            
            # Process all tweet categories
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
            self.logger.error(f"Failed to search tweets with query '{query}': {e}")
            return []
    
    async def _extract_comprehensive_data(self, url: str, target_tweet_id: str = None) -> Dict[str, Any]:
        """Extract comprehensive data using browser automation."""
        start_time = time.time()
        playwright = None
        browser = None
        context = None
        page = None
        
        # 获取Cookie管理器
        cookie_manager = get_cookie_manager()
        
        try:
            await self._rate_limit()
            
            self.logger.info(f"Starting comprehensive extraction for: {url}")
            
            # 获取cookies（简单直接，无验证）
            cookies = await cookie_manager.get_valid_cookies()
            
            playwright = await async_playwright().start()
            
            # Browser setup with enhanced settings
            proxy_config = None
            # Only use proxy if explicitly set via PLAYWRIGHT_PROXY
            proxy = os.getenv('PLAYWRIGHT_PROXY')
            if proxy:
                # Ensure proxy URL is properly formatted
                if not proxy.startswith(('http://', 'https://', 'socks5://')):
                    proxy = f"http://{proxy}"
                
                proxy_config = {"server": proxy}
                self.logger.info(f"Using proxy: {proxy}")
                
                # For HTTPS sites through HTTP proxy, ensure bypass is not set
                # Most HTTP proxies support HTTPS via CONNECT method
            
            # Get headless setting from environment
            headless = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
            
            browser = await playwright.chromium.launch(
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
            )
            
            context = await browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            )
            
            # Load cookies (already obtained before browser launch)
            if cookies:
                try:
                    await context.add_cookies(cookies)
                    self.logger.info(f"Loaded {len(cookies)} validated Twitter cookies")
                except Exception as e:
                    self.logger.warning(f"Failed to add cookies to context: {e}")
            else:
                self.logger.warning("No valid cookies available - running without authentication")
            
            page = await context.new_page()
            
            # Enhanced anti-detection
            await page.add_init_script("""
                // Remove webdriver traces
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                
                // Mock chrome object
                window.chrome = { runtime: {} };
                
                // Override permission API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Mock screen properties
                Object.defineProperty(screen, 'availWidth', { get: () => 1366 });
                Object.defineProperty(screen, 'availHeight', { get: () => 768 });
            """)
            
            # Navigate with multiple strategies
            response = await page.goto(url, wait_until='domcontentloaded', timeout=25000)
            
            if response and response.status >= 400:
                raise DataSourceError(f"HTTP error: {response.status}")
            
            # Verify we're on Twitter
            current_url = page.url
            if not any(domain in current_url for domain in ['x.com', 'twitter.com']):
                raise DataSourceError(f"Navigation failed, ended up at: {current_url}")
            
            # Use comprehensive extractor
            extractor = TweetDataExtractor(page)
            comprehensive_data = await extractor.extract_all_data(target_tweet_id)
            
            # Add extraction metadata
            comprehensive_data['extraction_metadata'].update({
                'source': 'Playwright',
                'page_load_time': f"{(time.time() - start_time):.2f}s" if 'start_time' in locals() else 'unknown',
                'final_url': current_url
            })
            
            tweet_count = (
                (1 if comprehensive_data.get('primary_tweet') else 0) +
                len(comprehensive_data.get('thread_tweets', [])) +
                len(comprehensive_data.get('related_tweets', []))
            )
            
            self.logger.info(f"Comprehensive extraction complete: {tweet_count} tweets extracted")
            
            return comprehensive_data
            
        finally:
            await self._cleanup_browser_resources(page, context, browser, playwright)
    
    def _extract_matching_tweets(self, comprehensive_data: Dict[str, Any], requested_ids: List[str]) -> List[TweetData]:
        """Extract tweets that match the requested IDs from comprehensive data."""
        results = []
        requested_id_set = set(self._extract_tweet_id(tid) for tid in requested_ids)
        
        # Check primary tweet
        primary_tweet = comprehensive_data.get('primary_tweet')
        if primary_tweet and primary_tweet.get('tweet_id') in requested_id_set:
            results.append(self._convert_to_tweet_data(primary_tweet))
        
        # Check thread tweets
        for tweet in comprehensive_data.get('thread_tweets', []):
            if tweet.get('tweet_id') in requested_id_set:
                results.append(self._convert_to_tweet_data(tweet))
        
        # Check related tweets
        for tweet in comprehensive_data.get('related_tweets', []):
            if tweet.get('tweet_id') in requested_id_set:
                results.append(self._convert_to_tweet_data(tweet))
        
        return results
    
    def _convert_to_tweet_data(self, tweet_dict: Dict[str, Any], fallback_id: str = None) -> TweetData:
        """Convert comprehensive tweet data to TweetData format."""
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
        """Extract tweet ID from Twitter URL."""
        import re
        match = re.search(r'/status/(\d+)', url)
        return match.group(1) if match else None
    
    async def _cleanup_browser_resources(self, page, context, browser, playwright):
        """Clean up browser resources safely."""
        cleanup_errors = []
        
        try:
            if page:
                await page.close()
        except Exception as e:
            cleanup_errors.append(f"Page: {e}")
        
        try:
            if context:
                await context.close()
        except Exception as e:
            cleanup_errors.append(f"Context: {e}")
        
        try:
            if browser:
                await browser.close()
        except Exception as e:
            cleanup_errors.append(f"Browser: {e}")
        
        try:
            if playwright:
                await playwright.stop()
        except Exception as e:
            cleanup_errors.append(f"Playwright: {e}")
        
        if cleanup_errors:
            self.logger.warning(f"Cleanup errors: {'; '.join(cleanup_errors)}")
    
