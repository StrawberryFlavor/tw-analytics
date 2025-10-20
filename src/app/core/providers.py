"""
服务提供者
负责注册和配置所有服务
"""

import os
from typing import Optional

from .container import ServiceContainer, ServiceProvider, ConfigProvider
from .interfaces import (
    DataSourceInterface, 
    DataSourceManagerInterface,
    TwitterServiceInterface,
    AsyncRunnerInterface,
    ResponseFormatterInterface,
    ConfigInterface
)


class TwitterServiceProvider(ServiceProvider):
    """Twitter服务提供者"""
    
    def register(self, container: ServiceContainer) -> None:
        """注册Twitter相关服务"""
        
        # 注册配置服务
        def create_config(c: ServiceContainer) -> ConfigInterface:
            config = ConfigProvider()
            # 从环境变量加载配置
            config.update({
                'TWITTER_BEARER_TOKEN': os.getenv('TWITTER_BEARER_TOKEN'),
                'PLAYWRIGHT_HEADLESS': os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true',
                'PLAYWRIGHT_PROXY': os.getenv('PLAYWRIGHT_PROXY'),
                'TWITTER_USERNAME': os.getenv('TWITTER_USERNAME'),
                'TWITTER_PASSWORD': os.getenv('TWITTER_PASSWORD'),
                # Apify配置
                'APIFY_API_TOKEN': os.getenv('APIFY_API_TOKEN'),
                'APIFY_ACTOR_ID': os.getenv('APIFY_ACTOR_ID', 'apidojo/tweet-scraper'),
                'APIFY_TIMEOUT': int(os.getenv('APIFY_TIMEOUT', '120')),
                'APIFY_ENABLE': os.getenv('APIFY_ENABLE', 'false').lower() == 'true',
                # 数据源优先级配置
                'DATA_SOURCE_PRIORITY': os.getenv('DATA_SOURCE_PRIORITY', 'playwright,apify,twitter_api'),
                # 浏览器池配置
                # 简化的浏览器池配置
                'BROWSER_POOL_MIN_SIZE': os.getenv('BROWSER_POOL_MIN_SIZE', '2'),
                'BROWSER_POOL_MAX_SIZE': os.getenv('BROWSER_POOL_MAX_SIZE', '6'),
                'BROWSER_POOL_MAX_CONCURRENT_REQUESTS': os.getenv('BROWSER_POOL_MAX_CONCURRENT_REQUESTS', '3'),
                'BROWSER_POOL_REQUEST_TIMEOUT': os.getenv('BROWSER_POOL_REQUEST_TIMEOUT', '120'),
                'BROWSER_POOL_INSTANCE_LIFETIME': os.getenv('BROWSER_POOL_INSTANCE_LIFETIME', '1800'),
                'BROWSER_POOL_ROTATION_ENABLED': os.getenv('BROWSER_POOL_ROTATION_ENABLED', 'true').lower() == 'true',
                'BROWSER_POOL_ANTI_DETECTION_LEVEL': os.getenv('BROWSER_POOL_ANTI_DETECTION_LEVEL', 'medium'),
            })
            return config
        
        container.register_singleton('config', create_config)
        
        # 注册异步运行器
        def create_async_runner(c: ServiceContainer) -> AsyncRunnerInterface:
            from ..services.utils.async_runner import AsyncRunner
            return AsyncRunner("main")
        
        container.register_singleton('async_runner', create_async_runner)
        
        # 注册数据源
        def create_twitter_api_source(c: ServiceContainer) -> DataSourceInterface:
            from ..services.data_sources.twitter_api import TwitterAPISource
            config = c.get('config')
            # 传入配置而不是依赖Flask
            return TwitterAPISource(bearer_token=config.get('TWITTER_BEARER_TOKEN'))
        
        def create_playwright_source(c: ServiceContainer) -> DataSourceInterface:
            from ..services.data_sources.playwright_pooled import PlaywrightPooledSource
            config = c.get('config')
            # 使用池化版本，传入池配置参数
            return PlaywrightPooledSource(
                pool_min_size=int(config.get('BROWSER_POOL_MIN_SIZE', 2)),
                pool_max_size=int(config.get('BROWSER_POOL_MAX_SIZE', 6)),
                max_concurrent_requests=int(config.get('BROWSER_POOL_MAX_CONCURRENT_REQUESTS', 3))
            )
        
        def create_apify_source(c: ServiceContainer) -> Optional[DataSourceInterface]:
            from ..services.data_sources.apify_source import ApifyTwitterSource
            config = c.get('config')
            
            # 只有在启用并配置了API令牌时才创建
            if config.get('APIFY_ENABLE') and config.get('APIFY_API_TOKEN'):
                return ApifyTwitterSource(
                    api_token=config.get('APIFY_API_TOKEN'),
                    actor_id=config.get('APIFY_ACTOR_ID', 'apidojo/tweet-scraper'),
                    timeout=config.get('APIFY_TIMEOUT', 120)
                )
            return None
        
        container.register_singleton('twitter_api_source', create_twitter_api_source)
        container.register_singleton('playwright_source', create_playwright_source)
        container.register_singleton('apify_source', create_apify_source)
        
        # 注册数据源管理器
        def create_data_source_manager(c: ServiceContainer) -> DataSourceManagerInterface:
            from ..services.data_sources.manager import DataSourceManager
            
            # 获取数据源优先级配置
            config = c.get('config')
            priority_config = config.get('DATA_SOURCE_PRIORITY', 'playwright,apify,twitter_api')
            priority_list = [name.strip().lower() for name in priority_config.split(',')]
            
            # 创建数据源映射表
            source_map = {}
            
            # Playwright数据源
            try:
                playwright_source = c.get('playwright_source')
                if playwright_source:
                    source_map['playwright'] = playwright_source
            except Exception:
                pass
            
            # Apify数据源
            try:
                apify_source = c.get('apify_source')
                if apify_source:
                    source_map['apify'] = apify_source
            except Exception:
                pass
                
            # TwitterAPI数据源
            try:
                twitter_api_source = c.get('twitter_api_source')
                if twitter_api_source:
                    source_map['twitter_api'] = twitter_api_source
            except Exception:
                pass
            
            # 根据优先级配置排序数据源
            sources = []
            for source_name in priority_list:
                if source_name in source_map:
                    sources.append(source_map[source_name])
            
            # 记录实际使用的数据源顺序
            source_names = [source.name for source in sources]
            print(f"数据源优先级: {' > '.join(source_names)}")
            
            return DataSourceManager(sources=sources)
        
        container.register_singleton('data_source_manager', create_data_source_manager)
        
        # 注册Twitter服务
        def create_twitter_service(c: ServiceContainer) -> TwitterServiceInterface:
            from ..services.twitter.service import TwitterService
            # 注入依赖
            service = TwitterService(
                data_manager=c.get('data_source_manager'),
                async_runner=c.get('async_runner')
            )
            return service
        
        container.register_singleton('twitter_service', create_twitter_service)
        
        # 注册响应格式化器
        def create_response_formatter(c: ServiceContainer) -> ResponseFormatterInterface:
            from ..services.formatters import TweetResponseFormatter
            return TweetResponseFormatter()
        
        container.register_transient('response_formatter', create_response_formatter)


class FlaskIntegrationProvider(ServiceProvider):
    """Flask集成提供者"""
    
    def __init__(self, app):
        self.app = app
    
    def register(self, container: ServiceContainer) -> None:
        """注册Flask相关服务"""
        
        # 注册Flask应用
        container.register_singleton('flask_app', lambda c: self.app)
        
        # 覆盖配置服务，使用Flask配置
        def create_flask_config(c: ServiceContainer) -> ConfigInterface:
            app = c.get('flask_app')
            
            class FlaskConfigAdapter(ConfigProvider):
                def get(self, key: str, default=None):
                    return app.config.get(key, default)
                
                def get_required(self, key: str):
                    value = app.config.get(key)
                    if value is None:
                        raise ValueError(f"Required config '{key}' not found")
                    return value
            
            return FlaskConfigAdapter()
        
        container.register_singleton('config', create_flask_config)