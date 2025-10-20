"""
浏览器池模块

提供高效的浏览器实例池化管理，支持并发请求处理和资源优化
"""

from .browser_instance import PooledBrowserInstance, InstanceStatus
from .browser_pool import BrowserPool
from .recovery_manager import RecoveryManager, FailureType, RecoveryAction

__all__ = [
    'PooledBrowserInstance',
    'InstanceStatus', 
    'BrowserPool',
    'RecoveryManager',
    'FailureType',
    'RecoveryAction'
]