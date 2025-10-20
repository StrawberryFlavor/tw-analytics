"""
数据库操作服务

遵循SOLID原则，提供对campaign_tweet_snapshot表的CRUD操作
警告：此服务连接线上数据库，请谨慎使用写入操作！
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from .connection_manager import DatabaseManager
from .models import CampaignTweetSnapshot, CampaignTweetSnapshotQuery


class DatabaseService:
    """数据库操作服务 - 单一职责原则"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db_manager = None
        
    async def _get_db_manager(self) -> DatabaseManager:
        """获取数据库管理器实例 - 延迟初始化"""
        if self._db_manager is None:
            self._db_manager = DatabaseManager()
            await self._db_manager.initialize()
        return self._db_manager
    
    # ============ 查询操作（安全，只读） ============
    
    async def get_by_id(self, record_id: int) -> Optional[CampaignTweetSnapshot]:
        """根据ID查询单条记录"""
        try:
            db_manager = await self._get_db_manager()
            
            query = "SELECT * FROM campaign_tweet_snapshot WHERE id = %s"
            results = await db_manager.execute_query(query, (record_id,))
            
            if results:
                return CampaignTweetSnapshot.from_dict(results[0])
            return None
            
        except Exception as e:
            self.logger.error(f"根据ID查询记录失败 (id={record_id}): {e}")
            raise
    
    async def get_by_tweet_id(self, tweet_id: str) -> Optional[CampaignTweetSnapshot]:
        """根据tweet_id查询单条记录"""
        try:
            db_manager = await self._get_db_manager()
            
            query = "SELECT * FROM campaign_tweet_snapshot WHERE tweet_id = %s ORDER BY created_at DESC LIMIT 1"
            results = await db_manager.execute_query(query, (tweet_id,))
            
            if results:
                return CampaignTweetSnapshot.from_dict(results[0])
            return None
            
        except Exception as e:
            self.logger.error(f"根据tweet_id查询记录失败 (tweet_id={tweet_id}): {e}")
            raise
    
    async def get_by_author(self, author_username: str, limit: int = 50) -> List[CampaignTweetSnapshot]:
        """根据作者查询多条记录"""
        try:
            db_manager = await self._get_db_manager()
            
            query = """
                SELECT * FROM campaign_tweet_snapshot 
                WHERE author_username = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            results = await db_manager.execute_query(query, (author_username, limit))
            
            return [CampaignTweetSnapshot.from_dict(row) for row in results]
            
        except Exception as e:
            self.logger.error(f"根据作者查询记录失败 (author={author_username}): {e}")
            raise
    
    async def get_recent_records(self, limit: int = 100, success_only: bool = True) -> List[CampaignTweetSnapshot]:
        """获取最近的记录"""
        try:
            db_manager = await self._get_db_manager()
            
            if success_only:
                query = """
                    SELECT * FROM campaign_tweet_snapshot 
                    WHERE success = 1 
                    ORDER BY created_at DESC 
                    LIMIT %s
                """
                params = (limit,)
            else:
                query = """
                    SELECT * FROM campaign_tweet_snapshot 
                    ORDER BY created_at DESC 
                    LIMIT %s
                """
                params = (limit,)
            
            results = await db_manager.execute_query(query, params)
            
            return [CampaignTweetSnapshot.from_dict(row) for row in results]
            
        except Exception as e:
            self.logger.error(f"获取最近记录失败 (limit={limit}): {e}")
            raise
    
    async def get_by_time_range(self, start_time: datetime, end_time: datetime, 
                               limit: int = 1000) -> List[CampaignTweetSnapshot]:
        """根据时间范围查询记录"""
        try:
            db_manager = await self._get_db_manager()
            
            query = """
                SELECT * FROM campaign_tweet_snapshot 
                WHERE tweet_time_utc BETWEEN %s AND %s 
                ORDER BY tweet_time_utc DESC 
                LIMIT %s
            """
            results = await db_manager.execute_query(query, (start_time, end_time, limit))
            
            return [CampaignTweetSnapshot.from_dict(row) for row in results]
            
        except Exception as e:
            self.logger.error(f"根据时间范围查询失败 (start={start_time}, end={end_time}): {e}")
            raise
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        try:
            db_manager = await self._get_db_manager()
            
            # 总记录数
            total_query = "SELECT COUNT(*) as total FROM campaign_tweet_snapshot"
            total_result = await db_manager.execute_query(total_query)
            total_count = total_result[0]['total'] if total_result else 0
            
            # 成功记录数
            success_query = "SELECT COUNT(*) as success FROM campaign_tweet_snapshot WHERE success = 1"
            success_result = await db_manager.execute_query(success_query)
            success_count = success_result[0]['success'] if success_result else 0
            
            # 最近7天记录数
            recent_query = """
                SELECT COUNT(*) as recent 
                FROM campaign_tweet_snapshot 
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            """
            recent_result = await db_manager.execute_query(recent_query)
            recent_count = recent_result[0]['recent'] if recent_result else 0
            
            # 前10位活跃作者
            top_authors_query = """
                SELECT author_username, COUNT(*) as count 
                FROM campaign_tweet_snapshot 
                WHERE success = 1 
                GROUP BY author_username 
                ORDER BY count DESC 
                LIMIT 10
            """
            top_authors = await db_manager.execute_query(top_authors_query)
            
            return {
                'total_records': total_count,
                'success_records': success_count,
                'failure_records': total_count - success_count,
                'success_rate': round(success_count / total_count * 100, 2) if total_count > 0 else 0,
                'recent_7days': recent_count,
                'top_authors': top_authors
            }
            
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            raise
    
    async def execute_custom_query(self, query_builder: CampaignTweetSnapshotQuery) -> List[CampaignTweetSnapshot]:
        """执行自定义查询（使用查询构建器）"""
        try:
            db_manager = await self._get_db_manager()
            
            query, params = query_builder.build()
            self.logger.info(f"执行自定义查询: {query}")
            
            results = await db_manager.execute_query(query, params)
            
            return [CampaignTweetSnapshot.from_dict(row) for row in results]
            
        except Exception as e:
            self.logger.error(f"执行自定义查询失败: {e}")
            raise
    
    # ============ 写入操作（危险，需谨慎使用） ============
    # 注意：以下操作会修改线上数据库，请确保在安全环境中使用！
    
    async def create_record(self, record: CampaignTweetSnapshot) -> int:
        """
        创建新记录
        
        警告：此操作会写入线上数据库！请确保数据正确！
        
        Returns:
            新记录的ID
        """
        try:
            # 验证数据
            is_valid, error_msg = record.is_valid()
            if not is_valid:
                raise ValueError(f"数据验证失败: {error_msg}")
            
            db_manager = await self._get_db_manager()
            
            query, params = record.get_insert_query()
            
            self.logger.warning(f"警告：即将执行写入操作到线上数据库！查询: {query}")
            
            # 执行插入并获取新ID
            async with db_manager.get_connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(query, params)
                    await connection.commit()
                    
                    new_id = cursor.lastrowid
                    self.logger.info(f"成功创建记录，ID: {new_id}")
                    
                    return new_id
                    
        except Exception as e:
            self.logger.error(f"创建记录失败: {e}")
            raise
    
    async def update_record(self, record: CampaignTweetSnapshot) -> bool:
        """
        更新记录
        
        警告：此操作会修改线上数据库！请确保数据正确！
        
        Returns:
            是否成功更新
        """
        try:
            if record.id is None:
                raise ValueError("更新记录必须提供ID")
            
            # 验证数据
            is_valid, error_msg = record.is_valid()
            if not is_valid:
                raise ValueError(f"数据验证失败: {error_msg}")
            
            db_manager = await self._get_db_manager()
            
            query, params = record.get_update_query()
            
            self.logger.warning(f"警告：即将执行更新操作到线上数据库！查询: {query}")
            
            affected_rows = await db_manager.execute_update(query, params)
            
            success = affected_rows > 0
            if success:
                self.logger.info(f"成功更新记录 ID: {record.id}")
            else:
                self.logger.warning(f"未找到要更新的记录 ID: {record.id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"更新记录失败: {e}")
            raise
    
    async def update_success_status(self, tweet_id: str, success: bool, message: str = None) -> bool:
        """
        更新推文的成功状态
        
        警告：此操作会修改线上数据库！
        """
        try:
            db_manager = await self._get_db_manager()
            
            if message:
                query = """
                    UPDATE campaign_tweet_snapshot 
                    SET success = %s, message = %s 
                    WHERE tweet_id = %s
                """
                params = (success, message, tweet_id)
            else:
                query = """
                    UPDATE campaign_tweet_snapshot 
                    SET success = %s 
                    WHERE tweet_id = %s
                """
                params = (success, tweet_id)
            
            self.logger.warning(f"警告：即将更新推文状态到线上数据库！tweet_id: {tweet_id}")
            
            affected_rows = await db_manager.execute_update(query, params)
            
            success_updated = affected_rows > 0
            if success_updated:
                self.logger.info(f"成功更新推文状态 tweet_id: {tweet_id}")
            else:
                self.logger.warning(f"未找到要更新的推文 tweet_id: {tweet_id}")
                
            return success_updated
            
        except Exception as e:
            self.logger.error(f"更新推文状态失败: {e}")
            raise
    
    async def batch_create_records(self, records: List[CampaignTweetSnapshot]) -> List[int]:
        """
        批量创建记录
        
        警告：此操作会批量写入线上数据库！请确保数据正确！
        
        Returns:
            新创建记录的ID列表
        """
        try:
            if not records:
                return []
            
            # 验证所有记录
            for i, record in enumerate(records):
                is_valid, error_msg = record.is_valid()
                if not is_valid:
                    raise ValueError(f"第{i+1}条记录验证失败: {error_msg}")
            
            db_manager = await self._get_db_manager()
            
            self.logger.warning(f"警告：即将批量写入{len(records)}条记录到线上数据库！")
            
            new_ids = []
            
            async with db_manager.get_connection() as connection:
                async with connection.cursor() as cursor:
                    for record in records:
                        query, params = record.get_insert_query()
                        await cursor.execute(query, params)
                        new_ids.append(cursor.lastrowid)
                    
                    await connection.commit()
                    
            self.logger.info(f"成功批量创建{len(new_ids)}条记录")
            return new_ids
            
        except Exception as e:
            self.logger.error(f"批量创建记录失败: {e}")
            raise
    
    async def close(self):
        """关闭数据库连接"""
        if self._db_manager:
            await self._db_manager.close()
            self._db_manager = None


# 单例实例
_database_service = None

async def get_database_service() -> DatabaseService:
    """获取数据库服务单例"""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service