"""Twitter-specific data models and utilities."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime

# Import common utilities from utils module
from ..utils import extract_tweet_id, validate_tweet_id, validate_username


@dataclass
class TwitterMetrics:
    """Twitter-specific metrics data structure."""
    tweet_id: str
    views: Optional[int] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    engagement_rate: float = 0.0
    
    @property
    def total_interactions(self) -> int:
        """Get total interactions (likes + retweets + replies + quotes)."""
        return self.likes + self.retweets + self.replies + self.quotes
    
    def calculate_engagement_rate(self) -> float:
        """Calculate engagement rate based on views."""
        if not self.views or self.views == 0:
            return 0.0
        return (self.total_interactions / self.views) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tweet_id': self.tweet_id,
            'views': self.views,
            'likes': self.likes,  
            'retweets': self.retweets,
            'replies': self.replies,
            'quotes': self.quotes,
            'total_interactions': self.total_interactions,
            'engagement_rate': self.calculate_engagement_rate()
        }


@dataclass 
class UserProfile:
    """Twitter user profile data structure."""
    user_id: str
    username: str
    display_name: str
    description: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    tweet_count: int = 0
    listed_count: int = 0
    verified: bool = False
    profile_image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'display_name': self.display_name,
            'description': self.description,
            'followers_count': self.followers_count,
            'following_count': self.following_count,
            'tweet_count': self.tweet_count,
            'listed_count': self.listed_count,
            'verified': self.verified,
            'profile_image_url': self.profile_image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class TweetInfo:
    """Complete tweet information."""
    tweet_id: str
    text: str
    author: UserProfile
    created_at: datetime
    metrics: TwitterMetrics
    url: str
    language: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tweet_id': self.tweet_id,
            'text': self.text,
            'author': self.author.to_dict(),
            'created_at': self.created_at.isoformat(),
            'metrics': self.metrics.to_dict(),
            'url': self.url,
            'language': self.language
        }


# Re-export utility functions for backward compatibility
__all__ = [
    'TwitterMetrics',
    'UserProfile', 
    'TweetInfo',
    'extract_tweet_id',
    'validate_tweet_id',
    'validate_username'
]