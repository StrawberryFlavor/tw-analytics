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
            from ..services.data_sources.playwright import PlaywrightSource
            config = c.get('config')
            # 可以传入配置参数
            return PlaywrightSource()
        
        container.register_transient('twitter_api_source', create_twitter_api_source)
        container.register_transient('playwright_source', create_playwright_source)
        
        # 注册数据源管理器
        def create_data_source_manager(c: ServiceContainer) -> DataSourceManagerInterface:
            from ..services.data_sources.manager import DataSourceManager
            # 注入数据源而不是让管理器自己创建
            sources = []
            
            try:
                sources.append(c.get('twitter_api_source'))
            except Exception:
                pass
                
            try:
                sources.append(c.get('playwright_source'))
            except Exception:
                pass
            
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