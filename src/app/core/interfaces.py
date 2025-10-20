"""
核心接口定义
定义服务之间的契约，实现松耦合
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Protocol
from datetime import datetime


class DataSourceInterface(Protocol):
    """数据源接口"""
    
    @property
    def name(self) -> str:
        """数据源名称"""
        ...
    
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        ...
    
    async def get_tweet_data(self, tweet_id: str) -> 'TweetData':
        """获取推文数据"""
        ...
    
    async def get_user_data(self, username: str) -> 'UserData':
        """获取用户数据"""
        ...
    
    async def get_comprehensive_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """获取综合推文数据（如果支持）"""
        ...


class DataSourceManagerInterface(Protocol):
    """数据源管理器接口"""
    
    async def get_tweet_data(self, tweet_id: str) -> 'TweetData':
        """获取推文数据（自动选择可用数据源）"""
        ...
    
    async def batch_get_tweet_data(self, tweet_ids: List[str]) -> List['TweetData']:
        """批量获取推文数据"""
        ...
    
    async def get_comprehensive_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """获取综合推文数据"""
        ...
    
    def get_available_sources(self) -> List[DataSourceInterface]:
        """获取可用的数据源列表"""
        ...


class TwitterServiceInterface(Protocol):
    """Twitter服务接口"""
    
    async def get_tweet_metrics(self, tweet_id: str) -> 'TweetData':
        """获取推文指标"""
        ...
    
    async def get_comprehensive_data(self, tweet_url: str) -> Dict[str, Any]:
        """获取综合推文数据"""
        ...
    
    async def get_user_info(self, username: str) -> 'UserData':
        """获取用户信息"""
        ...


class ConfigInterface(Protocol):
    """配置接口"""
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        ...
    
    def get_required(self, key: str) -> Any:
        """获取必需的配置值（不存在则抛出异常）"""
        ...


class AsyncRunnerInterface(Protocol):
    """异步运行器接口"""
    
    def run(self, coro, timeout: Optional[float] = None) -> Any:
        """在同步上下文中运行异步协程"""
        ...
    
    async def close(self) -> None:
        """关闭运行器"""
        ...


class ResponseFormatterInterface(Protocol):
    """响应格式化器接口"""
    
    def format_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化为优化响应"""
        ...


# 数据模型（这些应该移到单独的models.py文件）
from dataclasses import dataclass


@dataclass
class TweetData:
    """推文数据模型"""
    tweet_id: str
    text: str
    author_username: str
    author_name: str
    created_at: str
    public_metrics: Dict[str, int]
    view_count: Optional[int] = None
    url: Optional[str] = None
    lang: Optional[str] = None


@dataclass  
class UserData:
    """用户数据模型"""
    user_id: str
    username: str
    name: str
    description: Optional[str] = None
    public_metrics: Optional[Dict[str, int]] = None
    profile_image_url: Optional[str] = None
    verified: bool = False
    created_at: Optional[str] = None