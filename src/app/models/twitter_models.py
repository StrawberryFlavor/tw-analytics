"""
Twitter数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict


@dataclass
class TwitterData:
    """推特数据模型"""
    
    tweet_id: str
    text: str
    author_id: str
    author_username: str
    created_at: datetime
    public_metrics: Dict[str, int]
    
    @property
    def view_count(self) -> int:
        """获取浏览量"""
        return self.public_metrics.get('impression_count', 0)
    
    @property
    def like_count(self) -> int:
        """获取点赞数"""
        return self.public_metrics.get('like_count', 0)
    
    @property
    def retweet_count(self) -> int:
        """获取转发数"""
        return self.public_metrics.get('retweet_count', 0)
    
    @property
    def reply_count(self) -> int:
        """获取回复数"""
        return self.public_metrics.get('reply_count', 0)
    
    @property
    def quote_count(self) -> int:
        """获取引用数"""
        return self.public_metrics.get('quote_count', 0)


@dataclass
class UserData:
    """用户数据模型"""
    
    user_id: str
    username: str
    name: str
    description: Optional[str]
    followers_count: int
    following_count: int
    tweet_count: int
    created_at: datetime