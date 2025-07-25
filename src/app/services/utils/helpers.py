"""Common helper functions for Twitter services."""

import re
from typing import Optional


def extract_tweet_id(tweet_input: str) -> str:
    """
    Extract tweet ID from URL or return as-is if already an ID.
    
    Args:
        tweet_input: Tweet ID or Twitter URL
        
    Returns:
        Clean tweet ID
        
    Examples:
        >>> extract_tweet_id('1234567890123456789')
        '1234567890123456789'
        >>> extract_tweet_id('https://twitter.com/user/status/1234567890123456789')
        '1234567890123456789'
        >>> extract_tweet_id('https://x.com/user/status/1234567890123456789?s=20')
        '1234567890123456789'
    """
    if not tweet_input:
        return tweet_input
        
    # Check if it's a URL
    if 'twitter.com' in tweet_input or 'x.com' in tweet_input:
        # Extract from URL: https://twitter.com/username/status/1234567890
        parts = tweet_input.strip('/').split('/')
        if 'status' in parts:
            status_index = parts.index('status')
            if status_index + 1 < len(parts):
                return parts[status_index + 1].split('?')[0]  # Remove query params
    
    # Return as-is, removing any query parameters
    return tweet_input.split('?')[0].strip()


def validate_tweet_id(tweet_id: str) -> bool:
    """
    Validate tweet ID format.
    
    Args:
        tweet_id: Tweet ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not tweet_id:
        return False
    return tweet_id.isdigit() and len(tweet_id) >= 10


def validate_username(username: str) -> bool:
    """
    Validate Twitter username format.
    
    Args:
        username: Username to validate (with or without @)
        
    Returns:
        True if valid, False otherwise
    """
    if not username:
        return False
        
    username = username.lstrip('@')
    
    # Twitter username rules:
    # - 1-15 characters
    # - Only letters, numbers, and underscores
    if not (1 <= len(username) <= 15):
        return False
        
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))


def parse_count_text(text: str) -> int:
    """
    Parse count text with K, M, B suffixes and Chinese suffixes (万, 千).
    
    Args:
        text: Text containing a number with optional suffix
        
    Returns:
        Parsed integer value
        
    Examples:
        >>> parse_count_text('1.5K')
        1500
        >>> parse_count_text('2.3M')
        2300000
        >>> parse_count_text('4.7万')
        47000
        >>> parse_count_text('857')
        857
    """
    if not text:
        return 0
    
    # Remove commas and spaces
    text = text.replace(',', '').replace(' ', '')
    
    # First try to extract Chinese format numbers (x.x万, x千)
    chinese_match = re.search(r'([\d.]+)\s*万', text)
    if chinese_match:
        try:
            return int(float(chinese_match.group(1)) * 10_000)
        except ValueError:
            pass
    
    chinese_match = re.search(r'([\d.]+)\s*千', text)
    if chinese_match:
        try:
            return int(float(chinese_match.group(1)) * 1_000)
        except ValueError:
            pass
    
    # Then try English format numbers (xK, xM, xB)
    english_numbers = re.findall(r'[\d.]+[KMB]?', text)
    
    if english_numbers:
        try:
            num_text = english_numbers[0]
            
            # Handle suffixes
            if num_text.endswith('K'):
                return int(float(num_text[:-1]) * 1_000)
            elif num_text.endswith('M'):
                return int(float(num_text[:-1]) * 1_000_000)
            elif num_text.endswith('B'):
                return int(float(num_text[:-1]) * 1_000_000_000)
            else:
                return int(float(num_text))
                
        except (ValueError, IndexError):
            pass
    
    # Finally try to extract any pure numbers
    pure_numbers = re.findall(r'\d+', text)
    if pure_numbers:
        try:
            return int(pure_numbers[0])
        except ValueError:
            pass
    
    return 0


def clean_username(username: str) -> str:
    """
    Clean username by removing @ prefix.
    
    Args:
        username: Username with or without @
        
    Returns:
        Username without @ prefix
    """
    return username.lstrip('@') if username else username


# 统一路径管理器已集成到其他模块中，此处移除未使用的导入


def extract_rate_limit_reset_time(exception) -> Optional[int]:
    """
    Extract rate limit reset time from Twitter API exception.
    
    Args:
        exception: Twitter API exception with response headers
        
    Returns:
        Reset time timestamp or None if not available
    """
    try:
        if hasattr(exception, 'response') and exception.response:
            headers = getattr(exception.response, 'headers', {})
            if 'x-rate-limit-reset' in headers:
                return int(headers['x-rate-limit-reset'])
    except (AttributeError, ValueError, TypeError):
        pass
    return None


def create_tweet_dict(tweet_data) -> dict:
    """
    Convert TweetData object to dictionary format.
    
    Args:
        tweet_data: TweetData object
        
    Returns:
        Dictionary representation of tweet data
    """
    return {
        'id': tweet_data.tweet_id,
        'text': tweet_data.text,
        'author': {
            'id': tweet_data.author_id,
            'username': tweet_data.author_username,
            'name': tweet_data.author_name
        },
        'created_at': tweet_data.created_at,
        'view_count': tweet_data.view_count,
        'public_metrics': tweet_data.public_metrics,
        'lang': tweet_data.lang,
        'url': tweet_data.url
    }


def handle_twitter_api_exceptions(func):
    """
    Decorator for consistent Twitter API exception handling.
    
    Args:
        func: Function that makes Twitter API calls
        
    Returns:
        Decorated function with exception handling
    """
    import functools
    import asyncio
    from ...core.exceptions import (
        RateLimitError, AuthenticationError, NotFoundError, DataSourceError
    )
    
    def _handle_exceptions(e):
        """Common exception handling logic"""
        try:
            import tweepy
        except ImportError:
            raise DataSourceError("tweepy package not installed")
            
        if isinstance(e, tweepy.NotFound):
            raise NotFoundError(f"Twitter resource not found: {e}")
        elif isinstance(e, tweepy.TooManyRequests):
            reset_time = extract_rate_limit_reset_time(e)
            raise RateLimitError("Twitter API rate limit exceeded", reset_time)
        elif isinstance(e, tweepy.Unauthorized):
            raise AuthenticationError("Twitter API authentication failed")
        elif isinstance(e, tweepy.TwitterServerError):
            raise DataSourceError(f"Twitter server error: {e}")
        else:
            raise DataSourceError(f"Unexpected error: {e}")
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _handle_exceptions(e)
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            _handle_exceptions(e)
    
    # 检查函数是否为协程
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper