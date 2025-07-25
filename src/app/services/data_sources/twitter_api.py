"""Twitter Official API data source implementation."""

import tweepy
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import BaseDataSource
from ...core.interfaces import TweetData, UserData, DataSourceInterface
from ...core.exceptions import (
    AuthenticationError, NotFoundError
)
from ..utils.helpers import (
    clean_username, 
    extract_rate_limit_reset_time,
    handle_twitter_api_exceptions
)


class TwitterAPISource(BaseDataSource, DataSourceInterface):
    """Twitter Official API data source implementation."""
    
    def __init__(self, bearer_token: Optional[str] = None):
        """
        Initialize Twitter API source with injected bearer token.
        
        Args:
            bearer_token: Twitter API bearer token (injected dependency)
        """
        super().__init__("TwitterAPI")
        self._bearer_token = bearer_token
        self._client: Optional[tweepy.Client] = None
    
    @property
    def client(self) -> tweepy.Client:
        """Get Twitter client instance (lazy initialization)."""
        if self._client is None:
            self._client = self._create_client()
        return self._client
    
    def _create_client(self) -> tweepy.Client:
        """Create Twitter API client."""
        if not self._bearer_token:
            raise AuthenticationError("Twitter bearer token not provided")
        
        try:
            return tweepy.Client(
                bearer_token=self._bearer_token,
                wait_on_rate_limit=False  # We handle rate limiting ourselves
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to initialize Twitter client: {str(e)}")
    
    async def get_comprehensive_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """
        Twitter API doesn't support comprehensive data extraction.
        Returns None to indicate this source doesn't support this feature.
        """
        return None
    
    @handle_twitter_api_exceptions
    async def get_tweet_data(self, tweet_id: str) -> TweetData:
        """Get tweet data by ID."""
        tweet_id = self._extract_tweet_id(tweet_id)
        
        if not self._validate_tweet_id(tweet_id):
            raise ValueError(f"Invalid tweet ID: {tweet_id}")
        
        try:
            response = self.client.get_tweet(
                tweet_id,
                expansions=['author_id'],
                tweet_fields=[
                    'created_at', 'public_metrics', 'author_id', 
                    'lang', 'context_annotations'
                ],
                user_fields=['username', 'name']
            )
            
            if not response.data:
                raise NotFoundError(f"Tweet {tweet_id} not found or not accessible")
            
            tweet = response.data
            author = None
            if response.includes and 'users' in response.includes:
                author = response.includes['users'][0]
            
            metrics = tweet.public_metrics or {}
            
            tweet_data = TweetData(
                tweet_id=tweet.id,
                text=tweet.text,
                author_username=author.username if author else 'unknown',
                author_name=author.name if author else 'Unknown',
                created_at=tweet.created_at.isoformat() if tweet.created_at else datetime.now().isoformat(),
                public_metrics={
                    'retweet_count': metrics.get('retweet_count', 0),
                    'like_count': metrics.get('like_count', 0),
                    'reply_count': metrics.get('reply_count', 0),
                    'quote_count': metrics.get('quote_count', 0)
                },
                view_count=metrics.get('impression_count'),
                url=f"https://twitter.com/{author.username if author else 'unknown'}/status/{tweet.id}",
                lang=tweet.lang
            )
            
            self.handle_success()
            
            self.logger.info(f"Successfully retrieved tweet {tweet_id} via Twitter API")
            self.logger.debug(f"Tweet metrics: views={tweet_data.view_count}, "
                            f"likes={tweet_data.public_metrics['like_count']}, "
                            f"retweets={tweet_data.public_metrics['retweet_count']}")
            
            return tweet_data
            
        except Exception as e:
            self.handle_error(e)
            # 重新抛出异常，让装饰器处理具体的异常类型转换
            raise
    
    @handle_twitter_api_exceptions
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List[TweetData]:
        """Batch get tweet data. Twitter API v2 supports batch operations."""
        if not tweet_ids:
            return []
        
        # Clean and validate tweet IDs
        valid_tweet_ids = []
        for tweet_id in tweet_ids:
            clean_id = self._extract_tweet_id(tweet_id)
            if self._validate_tweet_id(clean_id):
                valid_tweet_ids.append(clean_id)
        
        if not valid_tweet_ids:
            return []
        
        try:
            # Twitter API v2 supports up to 100 tweets per request
            batch_size = min(100, len(valid_tweet_ids))
            batch_ids = valid_tweet_ids[:batch_size]
            
            response = self.client.get_tweets(
                batch_ids,
                expansions=['author_id'],
                tweet_fields=[
                    'created_at', 'public_metrics', 'author_id',
                    'lang', 'context_annotations'
                ],
                user_fields=['username', 'name']
            )
            
            results = []
            
            if response.data:
                # Create user lookup for faster access
                user_lookup = {}
                if response.includes and 'users' in response.includes:
                    user_lookup = {user.id: user for user in response.includes['users']}
                
                for tweet in response.data:
                    author = user_lookup.get(tweet.author_id)
                    metrics = tweet.public_metrics or {}
                    
                    tweet_data = TweetData(
                        tweet_id=tweet.id,
                        text=tweet.text,
                        author_username=author.username if author else 'unknown',
                        author_name=author.name if author else 'Unknown',
                        created_at=tweet.created_at.isoformat() if tweet.created_at else datetime.now().isoformat(),
                        public_metrics={
                            'retweet_count': metrics.get('retweet_count', 0),
                            'like_count': metrics.get('like_count', 0),
                            'reply_count': metrics.get('reply_count', 0),
                            'quote_count': metrics.get('quote_count', 0)
                        },
                        view_count=metrics.get('impression_count'),
                        url=f"https://twitter.com/{author.username if author else 'unknown'}/status/{tweet.id}",
                        lang=tweet.lang
                    )
                    results.append(tweet_data)
            
            self.handle_success()
            self.logger.info(f"Successfully retrieved {len(results)} tweets via Twitter API batch operation")
            
            return results
            
        except Exception as e:
            self.handle_error(e)
            raise
    
    @handle_twitter_api_exceptions
    async def get_user_data(self, username: str) -> UserData:
        """Get user data by username."""
        username = clean_username(username)
        
        if not self._validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        try:
            response = self.client.get_user(
                username=username,
                user_fields=[
                    'created_at', 'description', 'public_metrics',
                    'profile_image_url', 'verified'
                ]
            )
            
            if not response.data:
                raise NotFoundError(f"User @{username} not found")
            
            user = response.data
            metrics = user.public_metrics or {}
            
            user_data = UserData(
                user_id=user.id,
                username=user.username,
                name=user.name,
                description=user.description,
                public_metrics={
                    'followers_count': metrics.get('followers_count', 0),
                    'following_count': metrics.get('following_count', 0),
                    'tweet_count': metrics.get('tweet_count', 0),
                    'listed_count': metrics.get('listed_count', 0)
                },
                profile_image_url=user.profile_image_url,
                verified=user.verified or False,
                created_at=user.created_at.isoformat() if user.created_at else None
            )
            
            self.handle_success()
            self.logger.info(f"Successfully retrieved user @{username} via Twitter API")
            
            return user_data
            
        except Exception as e:
            self.handle_error(e)
            raise
            
    
    @handle_twitter_api_exceptions
    async def get_user_tweets(self, username: str, max_results: int = 10) -> List[TweetData]:
        """Get user's recent tweets."""
        username = clean_username(username)
        
        if not self._validate_username(username):
            raise ValueError(f"Invalid username: {username}")
        
        try:
            # First get user ID
            user_response = self.client.get_user(username=username)
            if not user_response.data:
                raise NotFoundError(f"User @{username} not found")
            
            user_id = user_response.data.id
            
            # Get user tweets
            response = self.client.get_users_tweets(
                user_id,
                max_results=min(max_results, 100),
                tweet_fields=[
                    'created_at', 'public_metrics', 'author_id',
                    'lang', 'context_annotations'
                ]
            )
            
            results = []
            
            if response.data:
                for tweet in response.data:
                    metrics = tweet.public_metrics or {}
                    
                    tweet_data = TweetData(
                        tweet_id=tweet.id,
                        text=tweet.text,
                        author_username=username,
                        author_name=user_response.data.name,
                        created_at=tweet.created_at.isoformat() if tweet.created_at else datetime.now().isoformat(),
                        public_metrics={
                            'retweet_count': metrics.get('retweet_count', 0),
                            'like_count': metrics.get('like_count', 0),
                            'reply_count': metrics.get('reply_count', 0),
                            'quote_count': metrics.get('quote_count', 0)
                        },
                        view_count=metrics.get('impression_count'),
                        url=f"https://twitter.com/{username}/status/{tweet.id}",
                        lang=tweet.lang
                    )
                    results.append(tweet_data)
            
            self.handle_success()
            self.logger.info(f"Successfully retrieved {len(results)} tweets for @{username} via Twitter API")
            
            return results
            
        except Exception as e:
            self.handle_error(e)
            raise
            
    
    @handle_twitter_api_exceptions
    async def search_tweets(self, query: str, max_results: int = 10) -> List[TweetData]:
        """Search tweets by query."""
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")
        
        try:
            response = self.client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),
                expansions=['author_id'],
                tweet_fields=[
                    'created_at', 'public_metrics', 'author_id',
                    'lang', 'context_annotations'
                ],
                user_fields=['username', 'name']
            )
            
            results = []
            
            if response.data:
                # Create user lookup
                user_lookup = {}
                if response.includes and 'users' in response.includes:
                    user_lookup = {user.id: user for user in response.includes['users']}
                
                for tweet in response.data:
                    author = user_lookup.get(tweet.author_id)
                    metrics = tweet.public_metrics or {}
                    
                    tweet_data = TweetData(
                        tweet_id=tweet.id,
                        text=tweet.text,
                        author_username=author.username if author else 'unknown',
                        author_name=author.name if author else 'Unknown',
                        created_at=tweet.created_at.isoformat() if tweet.created_at else datetime.now().isoformat(),
                        public_metrics={
                            'retweet_count': metrics.get('retweet_count', 0),
                            'like_count': metrics.get('like_count', 0),
                            'reply_count': metrics.get('reply_count', 0),
                            'quote_count': metrics.get('quote_count', 0)
                        },
                        view_count=metrics.get('impression_count'),
                        url=f"https://twitter.com/{author.username if author else 'unknown'}/status/{tweet.id}",
                        lang=tweet.lang
                    )
                    results.append(tweet_data)
            
            self.handle_success()
            self.logger.info(f"Successfully searched tweets with query '{query}', found {len(results)} results via Twitter API")
            
            return results
            
        except Exception as e:
            self.handle_error(e)
            raise
            
