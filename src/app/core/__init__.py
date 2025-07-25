"""
核心模块
提供依赖注入和接口定义
"""

from .container import ServiceContainer, get_app_container, create_request_container
from .interfaces import (
    DataSourceInterface,
    DataSourceManagerInterface, 
    TwitterServiceInterface,
    ConfigInterface,
    AsyncRunnerInterface,
    ResponseFormatterInterface,
    TweetData,
    UserData
)
from .providers import TwitterServiceProvider, FlaskIntegrationProvider
from .exceptions import (
    TwitterServiceError,
    DataSourceError,
    DataSourceUnavailableError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    ValidationError
)

__all__ = [
    'ServiceContainer',
    'get_app_container', 
    'create_request_container',
    'DataSourceInterface',
    'DataSourceManagerInterface',
    'TwitterServiceInterface', 
    'ConfigInterface',
    'AsyncRunnerInterface',
    'ResponseFormatterInterface',
    'TweetData',
    'UserData',
    'TwitterServiceProvider', 
    'FlaskIntegrationProvider',
    'TwitterServiceError',
    'DataSourceError',
    'DataSourceUnavailableError',
    'RateLimitError',
    'AuthenticationError',
    'NotFoundError',
    'ValidationError'
]