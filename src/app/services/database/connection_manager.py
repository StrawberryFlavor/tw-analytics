"""
数据库连接管理器

遵循单一职责原则，专门负责数据库连接的创建、管理和释放
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
import aiomysql

from ...core.config_factory import get_db_config


class DatabaseManager:
    """数据库连接管理器 - 单例模式"""
    
    _instance: Optional['DatabaseManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.logger = logging.getLogger(__name__)
        self._pool: Optional[aiomysql.Pool] = None
        self._initialized = True
        
        self.logger.info("数据库管理器初始化完成")
    
    async def initialize(self) -> None:
        """初始化数据库连接池"""
        async with self._lock:
            if self._pool is not None:
                return
                
            try:
                db_config = get_db_config(production=True)  # 使用生产环境配置
                pool_params = db_config.get_pool_params()
                self.logger.info(f"正在连接数据库: {pool_params['host']}:{pool_params['port']}/{pool_params['db']}")
                
                # 创建连接池
                self._pool = await aiomysql.create_pool(
                    host=pool_params['host'],
                    port=pool_params['port'],
                    user=pool_params['user'],
                    password=pool_params['password'],
                    db=pool_params['db'],
                    charset=pool_params['charset'],
                    autocommit=pool_params['autocommit'],
                    connect_timeout=pool_params['connect_timeout'],
                    pool_recycle=3600,  # 1小时回收连接
                    minsize=pool_params['minsize'],
                    maxsize=pool_params['maxsize']
                )
                
                # 测试连接
                await self._test_connection()
                
                self.logger.info(f"数据库连接池创建成功，最大连接数: {pool_params['maxsize']}")
                
            except Exception as e:
                self.logger.error(f"数据库连接初始化失败: {e}")
                raise
    
    async def _test_connection(self) -> None:
        """测试数据库连接"""
        if self._pool is None:
            raise RuntimeError("连接池未初始化")
        
        try:
            async with self._pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    result = await cursor.fetchone()
                    if result[0] != 1:
                        raise RuntimeError("数据库连接测试失败")
                    
            self.logger.info("数据库连接测试成功")
            
        except Exception as e:
            self.logger.error(f"数据库连接测试失败: {e}")
            raise
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiomysql.Connection, None]:
        """获取数据库连接的上下文管理器"""
        if self._pool is None:
            await self.initialize()
        
        connection = None
        try:
            connection = await self._pool.acquire()
            yield connection
        except Exception as e:
            self.logger.error(f"数据库连接操作异常: {e}")
            if connection:
                await connection.rollback()
            raise
        finally:
            if connection:
                self._pool.release(connection)
    
    @asynccontextmanager
    async def get_cursor(self) -> AsyncGenerator[aiomysql.DictCursor, None]:
        """获取数据库游标的上下文管理器"""
        async with self.get_connection() as connection:
            cursor = None
            try:
                cursor = await connection.cursor(aiomysql.DictCursor)
                yield cursor
            finally:
                if cursor:
                    await cursor.close()
    
    async def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """执行查询并返回结果"""
        async with self.get_cursor() as cursor:
            await cursor.execute(query, params or ())
            return await cursor.fetchall()
    
    async def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """执行更新操作并返回影响的行数"""
        async with self.get_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, params or ())
                await connection.commit()
                return cursor.rowcount
    
    async def close(self) -> None:
        """关闭数据库连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self.logger.info("数据库连接池已关闭")
    
    def get_status(self) -> dict:
        """获取连接池状态"""
        if not self._pool:
            return {'status': 'not_initialized'}
        
        return {
            'status': 'active',
            'size': self._pool.size,
            'free_size': self._pool.freesize,
            'max_size': self._pool.maxsize,
            'min_size': self._pool.minsize
        }