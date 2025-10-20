"""
依赖注入容器
使用依赖注入模式解决服务间的紧密耦合问题
"""

from typing import Dict, Any, Type, Optional, Callable
from abc import ABC, abstractmethod
import logging


class ServiceContainer:
    """服务容器，管理所有服务的创建和依赖注入"""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._singleton_names: set = set()  # 跟踪哪些是单例服务
        self.logger = logging.getLogger(__name__)
    
    def register_singleton(self, name: str, factory: Callable) -> None:
        """注册单例服务"""
        self._factories[name] = factory
        self._singleton_names.add(name)
        self.logger.debug(f"Registered singleton service: {name}")
    
    def register_transient(self, name: str, factory: Callable) -> None:
        """注册瞬态服务（每次请求创建新实例）"""
        self._factories[name] = factory
        # 确保不在单例名称集合中
        self._singleton_names.discard(name)
        self.logger.debug(f"Registered transient service: {name}")
    
    def get(self, name: str) -> Any:
        """获取服务实例"""
        # 检查是否是单例且已经创建
        if name in self._singleton_names and name in self._singletons:
            self.logger.debug(f"Returning cached singleton: {name}")
            return self._singletons[name]
        
        # 检查是否有工厂方法
        if name not in self._factories:
            raise ValueError(f"Service '{name}' not registered")
        
        # 创建服务实例
        self.logger.debug(f"Creating new instance for: {name}")
        instance = self._factories[name](self)
        
        # 如果是单例，缓存起来
        if name in self._singleton_names:
            self._singletons[name] = instance
            self.logger.debug(f"Cached singleton instance: {name}")
        
        return instance
    
    def clear(self) -> None:
        """清除所有服务（用于测试）"""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        self._singleton_names.clear()


class ServiceProvider(ABC):
    """服务提供者基类"""
    
    @abstractmethod
    def register(self, container: ServiceContainer) -> None:
        """注册服务到容器"""
        pass


class ConfigProvider:
    """配置提供者，从环境或配置文件加载配置"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)
    
    def update(self, config: Dict[str, Any]) -> None:
        """更新配置"""
        self._config.update(config)


# 全局容器实例（应用级别）
_app_container: Optional[ServiceContainer] = None


def get_app_container() -> ServiceContainer:
    """获取应用级别的服务容器"""
    global _app_container
    if _app_container is None:
        _app_container = ServiceContainer()
    return _app_container


def create_request_container(app_container: ServiceContainer) -> ServiceContainer:
    """创建请求级别的服务容器（继承应用容器）"""
    request_container = ServiceContainer()
    # 可以实现容器继承逻辑
    return request_container