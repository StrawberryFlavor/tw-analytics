"""Base data source implementation."""

import logging
from abc import ABC
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ...core.interfaces import DataSourceInterface, TweetData
from ...core.exceptions import DataSourceError, RateLimitError
from ..utils.helpers import extract_tweet_id, validate_tweet_id, validate_username


class BaseDataSource(DataSourceInterface, ABC):
    """Base implementation for data sources with common functionality."""
    
    def __init__(self, name: str):
        self._name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._healthy = True
        self._last_error: Optional[Exception] = None
        self._error_count = 0
        self._last_success: Optional[datetime] = None
        self._rate_limit_reset: Optional[datetime] = None
        
    @property
    def name(self) -> str:
        """Data source name."""
        return self._name
    
    def is_available(self) -> bool:
        """Check if data source is available."""
        # Check if we're in rate limit period
        if self._rate_limit_reset and datetime.now() < self._rate_limit_reset:
            return False
        
        # Check general health
        return self._healthy and self._error_count < 5
    
    def handle_success(self):
        """Handle successful operation."""
        self._healthy = True
        self._error_count = 0
        self._last_success = datetime.now()
        self._last_error = None
        
    def handle_error(self, error: Exception):
        """Handle error and update health status."""
        self._last_error = error
        self._error_count += 1
        
        if isinstance(error, RateLimitError):
            # Set rate limit reset time
            if hasattr(error, 'reset_time') and error.reset_time:
                self._rate_limit_reset = datetime.fromtimestamp(error.reset_time)
            else:
                # Default 15 minutes if no reset time provided
                self._rate_limit_reset = datetime.now() + timedelta(minutes=15)
            
            self.logger.warning(f"Rate limited until {self._rate_limit_reset}")
        
        # Mark as unhealthy if too many consecutive errors
        if self._error_count >= 5:
            self._healthy = False
            self.logger.error(f"Data source {self.name} marked as unhealthy after {self._error_count} errors")
        
        self.logger.error(f"Error in {self.name}: {error}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status."""
        return {
            'name': self.name,
            'healthy': self._healthy,
            'available': self.is_available(),
            'error_count': self._error_count,
            'last_error': str(self._last_error) if self._last_error else None,
            'last_success': self._last_success.isoformat() if self._last_success else None,
            'rate_limit_reset': self._rate_limit_reset.isoformat() if self._rate_limit_reset else None
        }
    
    def reset_health(self):
        """Reset health status."""
        self._healthy = True
        self._error_count = 0
        self._last_error = None
        self._rate_limit_reset = None
        self.logger.info(f"Health status reset for {self.name}")
    
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List[TweetData]:
        """
        Default implementation of batch get tweet data.
        Subclasses can override for more efficient batch operations.
        """
        results = []
        for tweet_id in tweet_ids:
            try:
                tweet_data = await self.get_tweet_data(tweet_id)
                results.append(tweet_data)
            except Exception as e:
                self.logger.warning(f"Failed to get tweet {tweet_id}: {e}")
                # Continue with other tweets
                continue
        return results
    
    def _extract_tweet_id(self, tweet_input: str) -> str:
        """Extract tweet ID from URL or return as-is if already an ID."""
        return extract_tweet_id(tweet_input)
    
    def _validate_tweet_id(self, tweet_id: str) -> bool:
        """Validate tweet ID format."""
        return validate_tweet_id(tweet_id)
    
    def _validate_username(self, username: str) -> bool:
        """Validate username format."""
        return validate_username(username)