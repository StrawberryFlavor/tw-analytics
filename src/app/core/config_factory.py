"""
统一配置工厂 - 解决配置类重复问题

遵循SOLID原则：
- S: 单一职责 - 只负责配置管理
- O: 开闭原则 - 可扩展新的配置类型
- L: 里氏替换 - 所有配置类可互换
- I: 接口隔离 - 按需提供配置
- D: 依赖倒置 - 依赖配置接口而非具体实现
"""

import os
from typing import Dict, Any, Optional, TypeVar, Type
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# 类型定义
T = TypeVar('T', bound='BaseConfig')


class BaseConfig(ABC):
    """基础配置类 - 定义所有配置的通用接口"""
    
    @classmethod
    @abstractmethod
    def from_env(cls: Type[T]) -> T:
        """从环境变量创建配置"""
        pass
    
    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        """验证配置有效性"""
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        pass


@dataclass
class DatabaseConfig(BaseConfig):
    """数据库配置 - 统一管理所有数据库相关配置"""
    
    # 连接配置
    host: str = field(default_factory=lambda: os.getenv('DB_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(os.getenv('DB_PORT', '3306')))
    username: str = field(default_factory=lambda: os.getenv('DB_USERNAME', 'root'))
    password: str = field(default_factory=lambda: os.getenv('DB_PASSWORD', ''))
    database: str = field(default_factory=lambda: os.getenv('DB_NAME', 'tw_analytics'))
    
    # 连接池配置
    pool_size: int = field(default_factory=lambda: int(os.getenv('DB_POOL_SIZE', '10')))
    max_connections: int = field(default_factory=lambda: int(os.getenv('DB_MAX_CONNECTIONS', '20')))
    connection_timeout: int = field(default_factory=lambda: int(os.getenv('DB_CONNECTION_TIMEOUT', '30')))
    
    # 高级配置
    charset: str = field(default_factory=lambda: os.getenv('DB_CHARSET', 'utf8mb4'))
    autocommit: bool = field(default_factory=lambda: os.getenv('DB_AUTOCOMMIT', 'true').lower() == 'true')
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """从环境变量创建配置"""
        return cls()
    
    @classmethod
    def for_production(cls) -> 'DatabaseConfig':
        """生产环境配置"""
        return cls(
            host="nine-mysql-production.c94eqyo4iffa.ap-southeast-1.rds.amazonaws.com",
            port=3306,
            username="admin", 
            password="NINE2025ai",
            database="Binineex",
            pool_size=10,
            max_connections=20,
            connection_timeout=30
        )
    
    def get_connection_params(self) -> Dict[str, Any]:
        """获取连接参数 - 适配aiomysql.connect()"""
        return {
            'host': self.host,
            'port': self.port,
            'user': self.username,
            'password': self.password,
            'db': self.database,
            'charset': self.charset,
            'autocommit': self.autocommit,
            'connect_timeout': self.connection_timeout
            # 注意：pool_size和maxsize是create_pool的参数，不是connect的参数
        }
    
    def get_pool_params(self) -> Dict[str, Any]:
        """获取连接池参数 - 适配aiomysql.create_pool()"""
        base_params = self.get_connection_params()
        base_params.update({
            'minsize': 1,
            'maxsize': self.max_connections
        })
        return base_params
    
    def get_jdbc_url(self) -> str:
        """获取JDBC格式URL"""
        return f"jdbc:mysql://{self.host}:{self.port}/{self.database}?autoReconnect=true&useUnicode=true&characterEncoding=UTF-8&allowMultiQueries=true&useSSL=false"
    
    def validate(self) -> tuple[bool, str]:
        """验证配置有效性"""
        if not self.host:
            return False, "数据库主机不能为空"
        if not self.username:
            return False, "数据库用户名不能为空"
        if not self.database:
            return False, "数据库名不能为空"
        if self.port <= 0 or self.port > 65535:
            return False, "数据库端口必须在1-65535之间"
        if self.pool_size <= 0:
            return False, "连接池大小必须大于0"
        if self.max_connections < self.pool_size:
            return False, "最大连接数不能小于连接池大小"
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'pool_size': self.pool_size,
            'max_connections': self.max_connections,
            'connection_timeout': self.connection_timeout,
            'charset': self.charset,
            'autocommit': self.autocommit
        }


@dataclass
class UpdaterConfig(BaseConfig):
    """数据更新器配置 - 继承原有功能但遵循新的接口"""
    
    # 批处理配置
    batch_size: int = 10
    max_concurrent_batches: int = 2
    
    # 速率限制配置
    requests_per_minute: int = 30
    requests_per_hour: int = 1000
    
    # 延迟配置
    batch_delay_seconds: float = 2.0
    request_delay_seconds: float = 1.0
    error_retry_delay: float = 5.0
    
    # 重试配置
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    max_consecutive_failures: int = 5
    pause_on_error_seconds: float = 30.0
    
    # 进度配置
    progress_save_interval: int = 5
    enable_progress_logging: bool = True
    
    # 数据过滤配置
    skip_recent_updates: bool = True
    recent_update_threshold_hours: int = 24
    
    # 性能配置
    prefetch_buffer_size: int = 50
    connection_timeout: float = 30.0
    read_timeout: float = 60.0
    
    @classmethod
    def from_env(cls) -> 'UpdaterConfig':
        """从环境变量创建配置"""
        return cls(
            batch_size=int(os.getenv('UPDATER_BATCH_SIZE', '10')),
            max_concurrent_batches=int(os.getenv('UPDATER_MAX_CONCURRENT_BATCHES', '2')),
            requests_per_minute=int(os.getenv('UPDATER_REQUESTS_PER_MINUTE', '30')),
            requests_per_hour=int(os.getenv('UPDATER_REQUESTS_PER_HOUR', '1000')),
            batch_delay_seconds=float(os.getenv('UPDATER_BATCH_DELAY', '2.0')),
            request_delay_seconds=float(os.getenv('UPDATER_REQUEST_DELAY', '1.0')),
            error_retry_delay=float(os.getenv('UPDATER_ERROR_RETRY_DELAY', '5.0')),
            max_retries=int(os.getenv('UPDATER_MAX_RETRIES', '3')),
            retry_backoff_factor=float(os.getenv('UPDATER_RETRY_BACKOFF', '2.0')),
            max_consecutive_failures=int(os.getenv('UPDATER_MAX_FAILURES', '5')),
            pause_on_error_seconds=float(os.getenv('UPDATER_PAUSE_ON_ERROR', '30.0')),
            progress_save_interval=int(os.getenv('UPDATER_PROGRESS_INTERVAL', '5')),
            enable_progress_logging=os.getenv('UPDATER_ENABLE_LOGGING', 'true').lower() == 'true',
            skip_recent_updates=os.getenv('UPDATER_SKIP_RECENT', 'true').lower() == 'true',
            recent_update_threshold_hours=int(os.getenv('UPDATER_RECENT_THRESHOLD', '24')),
            prefetch_buffer_size=int(os.getenv('UPDATER_PREFETCH_BUFFER', '50')),
            connection_timeout=float(os.getenv('UPDATER_CONNECTION_TIMEOUT', '30.0')),
            read_timeout=float(os.getenv('UPDATER_READ_TIMEOUT', '60.0'))
        )
    
    @classmethod
    def create_safe_config(cls) -> 'UpdaterConfig':
        """创建安全的默认配置"""
        return cls(
            batch_size=5,
            max_concurrent_batches=1,
            requests_per_minute=15,
            requests_per_hour=900,
            batch_delay_seconds=3.0,
            request_delay_seconds=2.0,
            error_retry_delay=10.0,
            max_retries=2,
            max_consecutive_failures=3,
            pause_on_error_seconds=60.0,
            skip_recent_updates=True,
            recent_update_threshold_hours=12
        )
    
    @classmethod
    def create_fast_config(cls) -> 'UpdaterConfig':
        """创建快速配置"""
        return cls(
            batch_size=20,
            max_concurrent_batches=3,
            requests_per_minute=60,
            requests_per_hour=2000,
            batch_delay_seconds=0.5,
            request_delay_seconds=0.2,
            error_retry_delay=2.0,
            max_retries=5,
            skip_recent_updates=False
        )
    
    def get_effective_delay(self) -> float:
        """计算有效延迟"""
        min_delay_from_rate = 60.0 / self.requests_per_minute
        return max(self.request_delay_seconds, min_delay_from_rate)
    
    def validate(self) -> tuple[bool, str]:
        """验证配置有效性"""
        if self.batch_size <= 0:
            return False, "batch_size必须大于0"
        if self.batch_size > 100:
            return False, "batch_size不应超过100"
        if self.requests_per_minute <= 0:
            return False, "requests_per_minute必须大于0"
        if self.requests_per_hour <= 0:
            return False, "requests_per_hour必须大于0"
        if self.requests_per_minute > self.requests_per_hour / 60:
            return False, "每分钟请求数不能超过每小时请求数的1/60"
        if self.max_retries < 0:
            return False, "max_retries不能为负数"
        if self.retry_backoff_factor < 1.0:
            return False, "retry_backoff_factor必须至少为1.0"
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'batch_size': self.batch_size,
            'max_concurrent_batches': self.max_concurrent_batches,
            'requests_per_minute': self.requests_per_minute,
            'requests_per_hour': self.requests_per_hour,
            'batch_delay_seconds': self.batch_delay_seconds,
            'request_delay_seconds': self.request_delay_seconds,
            'effective_delay': self.get_effective_delay(),
            'error_retry_delay': self.error_retry_delay,
            'max_retries': self.max_retries,
            'retry_backoff_factor': self.retry_backoff_factor,
            'max_consecutive_failures': self.max_consecutive_failures,
            'pause_on_error_seconds': self.pause_on_error_seconds,
            'progress_save_interval': self.progress_save_interval,
            'enable_progress_logging': self.enable_progress_logging,
            'skip_recent_updates': self.skip_recent_updates,
            'recent_update_threshold_hours': self.recent_update_threshold_hours,
            'prefetch_buffer_size': self.prefetch_buffer_size,
            'connection_timeout': self.connection_timeout,
            'read_timeout': self.read_timeout
        }


@dataclass
class SyncConfig(BaseConfig):
    """数据同步配置"""
    
    # 同步批次配置
    sync_batch_size: int = 50
    max_concurrent_syncs: int = 3
    
    # 重试配置
    max_sync_retries: int = 3
    sync_retry_delay: float = 5.0
    
    # 超时配置
    sync_timeout: float = 30.0
    
    # 错误处理
    skip_invalid_records: bool = True
    mark_invalid_on_error: bool = True
    
    # 同步模式
    sync_mode: str = "missing_only"  # "missing_only", "update_all", "priority_new"
    dry_run: bool = False  # 演练模式
    enable_twitter_api: bool = True  # 启用Twitter API
    
    @classmethod
    def from_env(cls) -> 'SyncConfig':
        """从环境变量创建配置"""
        return cls(
            sync_batch_size=int(os.getenv('SYNC_BATCH_SIZE', '50')),
            max_concurrent_syncs=int(os.getenv('SYNC_MAX_CONCURRENT', '3')),
            max_sync_retries=int(os.getenv('SYNC_MAX_RETRIES', '3')),
            sync_retry_delay=float(os.getenv('SYNC_RETRY_DELAY', '5.0')),
            sync_timeout=float(os.getenv('SYNC_TIMEOUT', '30.0')),
            skip_invalid_records=os.getenv('SYNC_SKIP_INVALID', 'true').lower() == 'true',
            mark_invalid_on_error=os.getenv('SYNC_MARK_INVALID', 'true').lower() == 'true'
        )
    
    @classmethod
    def create_safe_config(cls) -> 'SyncConfig':
        """创建安全的同步配置"""
        return cls(
            sync_batch_size=20,
            max_concurrent_syncs=1,
            sync_retry_delay=2.0,
            sync_timeout=30.0,
            skip_invalid_records=True,
            mark_invalid_on_error=True,
            sync_mode="missing_only",
            dry_run=False,
            enable_twitter_api=True
        )
    
    @classmethod
    def create_update_all_config(cls) -> 'SyncConfig':
        """创建全部更新配置"""
        return cls(
            sync_batch_size=15,  # 更新现有记录用更小批次
            max_concurrent_syncs=1,
            sync_retry_delay=3.0,  # 更长延迟避免API限制
            sync_timeout=30.0,
            skip_invalid_records=True,
            mark_invalid_on_error=True,
            sync_mode="update_all",
            dry_run=False,
            enable_twitter_api=True
        )
    
    @classmethod
    def create_priority_config(cls) -> 'SyncConfig':
        """创建优先级同步配置 - 专门处理从未同步过的数据"""
        return cls(
            sync_batch_size=25,  # 新数据用更大批次提高效率
            max_concurrent_syncs=1,
            sync_retry_delay=1.5,  # 适中延迟
            sync_timeout=30.0,
            skip_invalid_records=True,
            mark_invalid_on_error=True,
            sync_mode="priority_new",
            dry_run=False,
            enable_twitter_api=True
        )
    
    def validate(self) -> tuple[bool, str]:
        """验证配置有效性"""
        if self.sync_batch_size <= 0:
            return False, "sync_batch_size必须大于0"
        if self.max_concurrent_syncs <= 0:
            return False, "max_concurrent_syncs必须大于0"
        if self.sync_timeout <= 0:
            return False, "sync_timeout必须大于0"
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'sync_batch_size': self.sync_batch_size,
            'max_concurrent_syncs': self.max_concurrent_syncs,
            'max_sync_retries': self.max_sync_retries,
            'sync_retry_delay': self.sync_retry_delay,
            'sync_timeout': self.sync_timeout,
            'skip_invalid_records': self.skip_invalid_records,
            'mark_invalid_on_error': self.mark_invalid_on_error
        }


class ConfigFactory:
    """配置工厂 - 统一管理所有配置的创建和获取"""
    
    _instances: Dict[str, BaseConfig] = {}
    
    @classmethod
    def get_database_config(cls, use_production: bool = None) -> DatabaseConfig:
        """获取数据库配置"""
        key = f"database_{'prod' if use_production else 'env'}"
        
        if key not in cls._instances:
            if use_production:
                cls._instances[key] = DatabaseConfig.for_production()
            else:
                cls._instances[key] = DatabaseConfig.from_env()
        
        return cls._instances[key]
    
    @classmethod
    def get_updater_config(cls, config_type: str = 'default') -> UpdaterConfig:
        """获取更新器配置"""
        key = f"updater_{config_type}"
        
        if key not in cls._instances:
            if config_type == 'safe':
                cls._instances[key] = UpdaterConfig.create_safe_config()
            elif config_type == 'fast':
                cls._instances[key] = UpdaterConfig.create_fast_config()
            else:
                cls._instances[key] = UpdaterConfig.from_env()
        
        return cls._instances[key]
    
    @classmethod
    def get_sync_config(cls) -> SyncConfig:
        """获取同步配置"""
        if 'sync' not in cls._instances:
            cls._instances['sync'] = SyncConfig.from_env()
        
        return cls._instances['sync']
    
    @classmethod
    def clear_cache(cls):
        """清空配置缓存"""
        cls._instances.clear()
    
    @classmethod
    def validate_all_configs(cls) -> Dict[str, tuple[bool, str]]:
        """验证所有已创建的配置"""
        results = {}
        for key, config in cls._instances.items():
            results[key] = config.validate()
        return results
    
    @classmethod
    def get_all_configs_dict(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有配置的字典表示"""
        return {key: config.to_dict() for key, config in cls._instances.items()}


# 便捷函数
def get_db_config(production: bool = None) -> DatabaseConfig:
    """获取数据库配置的便捷函数"""
    return ConfigFactory.get_database_config(production)


def get_updater_config(config_type: str = 'default') -> UpdaterConfig:
    """获取更新器配置的便捷函数"""
    return ConfigFactory.get_updater_config(config_type)


def get_sync_config() -> SyncConfig:
    """获取同步配置的便捷函数"""
    return ConfigFactory.get_sync_config()