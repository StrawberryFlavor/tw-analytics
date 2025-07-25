"""Twitter API client wrapper."""

import tweepy
import logging
from typing import Optional, List, Dict, Any
from flask import current_app

from ...core.exceptions import AuthenticationError, RateLimitError, NotFoundError, DataSourceError


class TwitterClient:
    """Twitter API client wrapper with enhanced error handling."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._client: Optional[tweepy.Client] = None
    
    @property
    def client(self) -> tweepy.Client:
        """Get Twitter API client instance (lazy initialization)."""
        if self._client is None:
            self._client = self._create_client()
        return self._client
    
    def _create_client(self) -> tweepy.Client:
        """Create Twitter API client."""
        bearer_token = current_app.config.get('TWITTER_BEARER_TOKEN')
        if not bearer_token:
            raise AuthenticationError("TWITTER_BEARER_TOKEN not configured")
        
        try:
            return tweepy.Client(
                bearer_token=bearer_token,
                wait_on_rate_limit=False  # We handle rate limiting at the service level
            )
        except Exception as e:
            raise AuthenticationError(f"Failed to initialize Twitter client: {str(e)}")
    
    def get_tweet(self, tweet_id: str, **kwargs) -> tweepy.Response:
        """
        Get tweet by ID with error handling.
        
        Args:
            tweet_id: Tweet ID
            **kwargs: Additional parameters for tweepy.Client.get_tweet
            
        Returns:
            tweepy.Response object
            
        Raises:
            NotFoundError: Tweet not found
            RateLimitError: Rate limit exceeded
            AuthenticationError: Authentication failed
            DataSourceError: Other API errors
        """
        try:
            response = self.client.get_tweet(tweet_id, **kwargs)
            
            if not response.data:
                raise NotFoundError(f"Tweet {tweet_id} not found or not accessible")
            
            return response
            
        except tweepy.NotFound:
            raise NotFoundError(f"Tweet {tweet_id} not found or not accessible")
        except tweepy.TooManyRequests as e:
            reset_time = self._extract_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        except tweepy.Unauthorized:
            raise AuthenticationError("Twitter API authentication failed")
        except Exception as e:
            raise DataSourceError(f"Twitter API error: {str(e)}")
    
    def get_tweets(self, tweet_ids: List[str], **kwargs) -> tweepy.Response:
        """
        Get multiple tweets by IDs.
        
        Args:
            tweet_ids: List of tweet IDs (max 100)
            **kwargs: Additional parameters for tweepy.Client.get_tweets
            
        Returns:
            tweepy.Response object
            
        Raises:
            RateLimitError: Rate limit exceeded
            AuthenticationError: Authentication failed
            DataSourceError: Other API errors
        """
        try:
            # Twitter API v2 supports max 100 tweets per request
            if len(tweet_ids) > 100:
                tweet_ids = tweet_ids[:100]
                self.logger.warning(f"Tweet IDs truncated to 100 (limit)")
            
            response = self.client.get_tweets(tweet_ids, **kwargs)
            return response
            
        except tweepy.TooManyRequests as e:
            reset_time = self._extract_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        except tweepy.Unauthorized:
            raise AuthenticationError("Twitter API authentication failed")
        except Exception as e:
            raise DataSourceError(f"Twitter API batch error: {str(e)}")
    
    def get_user(self, **kwargs) -> tweepy.Response:
        """
        Get user information.
        
        Args:
            **kwargs: Parameters for tweepy.Client.get_user (username, user_id, etc.)
            
        Returns:
            tweepy.Response object
            
        Raises:
            NotFoundError: User not found
            RateLimitError: Rate limit exceeded
            AuthenticationError: Authentication failed
            DataSourceError: Other API errors
        """
        try:
            response = self.client.get_user(**kwargs)
            
            if not response.data:
                user_identifier = kwargs.get('username') or kwargs.get('user_id', 'unknown')
                raise NotFoundError(f"User {user_identifier} not found")
            
            return response
            
        except tweepy.NotFound:
            user_identifier = kwargs.get('username') or kwargs.get('user_id', 'unknown')
            raise NotFoundError(f"User {user_identifier} not found")
        except tweepy.TooManyRequests as e:
            reset_time = self._extract_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        except tweepy.Unauthorized:
            raise AuthenticationError("Twitter API authentication failed")
        except Exception as e:
            raise DataSourceError(f"Twitter API user error: {str(e)}")
    
    def get_users_tweets(self, user_id: str, **kwargs) -> tweepy.Response:
        """
        Get user's tweets.
        
        Args:
            user_id: User ID
            **kwargs: Additional parameters for tweepy.Client.get_users_tweets
            
        Returns:
            tweepy.Response object
            
        Raises:
            NotFoundError: User not found
            RateLimitError: Rate limit exceeded
            AuthenticationError: Authentication failed
            DataSourceError: Other API errors
        """
        try:
            response = self.client.get_users_tweets(user_id, **kwargs)
            return response
            
        except tweepy.NotFound:
            raise NotFoundError(f"User {user_id} not found")
        except tweepy.TooManyRequests as e:
            reset_time = self._extract_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        except tweepy.Unauthorized:
            raise AuthenticationError("Twitter API authentication failed")
        except Exception as e:
            raise DataSourceError(f"Twitter API user tweets error: {str(e)}")
    
    def search_recent_tweets(self, query: str, **kwargs) -> tweepy.Response:
        """
        Search recent tweets.
        
        Args:
            query: Search query
            **kwargs: Additional parameters for tweepy.Client.search_recent_tweets
            
        Returns:
            tweepy.Response object
            
        Raises:
            RateLimitError: Rate limit exceeded
            AuthenticationError: Authentication failed
            DataSourceError: Other API errors
        """
        try:
            response = self.client.search_recent_tweets(query, **kwargs)
            return response
            
        except tweepy.TooManyRequests as e:
            reset_time = self._extract_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        except tweepy.Unauthorized:
            raise AuthenticationError("Twitter API authentication failed")
        except Exception as e:
            raise DataSourceError(f"Twitter API search error: {str(e)}")
    
    def _extract_reset_time(self, error: tweepy.TooManyRequests) -> Optional[int]:
        """Extract rate limit reset time from error response."""
        try:
            if hasattr(error.response, 'headers') and 'x-rate-limit-reset' in error.response.headers:
                return int(error.response.headers['x-rate-limit-reset'])
        except (AttributeError, ValueError, KeyError):
            pass
        return None
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status (if available).
        
        Returns:
            Dictionary with rate limit information
        """
        try:
            # This would require making a test request to get headers
            # For now, return empty dict
            return {}
        except Exception as e:
            self.logger.warning(f"Failed to get rate limit status: {e}")
            return {}