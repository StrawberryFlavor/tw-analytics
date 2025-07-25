"""
核心异常定义
提供统一的异常处理
"""

from typing import Optional


class TwitterServiceError(Exception):
    """Twitter服务基础异常"""
    pass


class DataSourceError(TwitterServiceError):
    """数据源错误"""
    pass


class DataSourceUnavailableError(DataSourceError):
    """数据源不可用错误"""
    pass


class RateLimitError(DataSourceError):
    """速率限制错误"""
    
    def __init__(self, message: str, reset_time: Optional[int] = None):
        super().__init__(message)
        self.reset_time = reset_time


class AuthenticationError(TwitterServiceError):
    """认证错误"""
    pass


class NotFoundError(TwitterServiceError):
    """资源未找到错误"""
    pass


class ValidationError(TwitterServiceError):
    """数据验证错误"""
    pass