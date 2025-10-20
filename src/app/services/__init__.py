"""Services module - unified interface for all services."""

# Core interfaces and exceptions
from ..core.interfaces import (
    DataSourceInterface,
    TwitterServiceInterface
)
from ..core.exceptions import (
    TwitterServiceError,
    DataSourceError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    ValidationError
)

# Data sources
from .data_sources import (
    BaseDataSource,
    TwitterAPISource,
    # PlaywrightSource,  # 已移除，统一使用PlaywrightPooledSource
    DataSourceManager
)

# Twitter services
from .twitter import (
    TwitterService,
    TwitterClient,
    TwitterMetrics,
    UserProfile
)

# Utilities
from .utils import (
    AsyncRunner,
    get_async_runner
)

# 注意：不再使用全局单例，现在通过依赖注入容器管理服务实例
# 如果需要访问服务，请通过 current_app.container.get('twitter_service') 获取

__all__ = [
    # Core interfaces
    'DataSourceInterface',
    'TwitterServiceInterface',
    
    # Exceptions
    'TwitterServiceError',
    'DataSourceError', 
    'RateLimitError',
    'AuthenticationError',
    'NotFoundError',
    'ValidationError',
    
    # Data sources
    'BaseDataSource',
    'TwitterAPISource',
    # 'PlaywrightSource',  # 已移除，统一使用PlaywrightPooledSource
    'DataSourceManager',
    
    # Twitter services
    'TwitterService',
    'TwitterClient',
    'TwitterMetrics',
    'UserProfile',
    
    # Utilities
    'AsyncRunner',
    'get_async_runner',
    
    # 注意：不再导出全局service实例，请使用依赖注入容器
]