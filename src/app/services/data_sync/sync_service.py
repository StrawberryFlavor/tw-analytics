"""
数据同步服务

负责从 campaign_task_submission 同步数据到 campaign_tweet_snapshot
"""

import asyncio
import inspect
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import aiomysql

from ..database import DatabaseService, CampaignTweetSnapshot
from .sync_models import TaskSubmission, SyncRecord, SyncOperation
from .error_handler import error_handler, ErrorCategory, ErrorAction
from ...core.config_factory import get_sync_config, SyncConfig
from ..data_sources.extractors.rate_limit_detector import rate_limit_detector


@dataclass
class SyncResult:
    """同步结果"""
    total_processed: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    processing_time: float = 0.0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_processed == 0:
            return 0.0
        return ((self.created_count + self.updated_count + self.skipped_count) / self.total_processed) * 100


class CampaignDataSyncService:
    """数据同步服务 - 单一职责原则"""
    
    def __init__(self, 
                 database_service: DatabaseService,
                 config: SyncConfig = None):
        """
        初始化同步服务
        
        Args:
            database_service: 数据库服务
            config: 同步配置
        """
        self.db_service = database_service
        self.config = config or get_sync_config()
        self.logger = logging.getLogger(__name__)
        self._twitter_service = None  # 缓存Twitter服务实例
        
        self.logger.info(f"🔄 数据同步服务初始化完成")
        self.logger.info(f"📋 配置: 批次大小={self.config.sync_batch_size}, 并发={self.config.max_concurrent_syncs}")
    
    async def _get_database_connection(self):
        """获取数据库连接 - 统一配置管理"""
        from ...core.config_factory import get_db_config
        
        db_config = get_db_config(production=True)
        connection_params = db_config.get_connection_params()
        
        return await aiomysql.connect(**connection_params)
    
    async def sync_all_data(self) -> SyncResult:
        """
        同步所有数据
        
        Returns:
            同步结果
        """
        start_time = time.time()
        result = SyncResult()
        
        try:
            self.logger.info("🔄 开始数据同步...")
            
            # 1. 分析需要同步的数据
            sync_records = await self._analyze_sync_needs()
            
            if not sync_records:
                self.logger.info("✅ 没有需要同步的数据")
                return result
            
            result.total_processed = len(sync_records)
            self.logger.info(f"📊 找到 {len(sync_records)} 条记录需要同步")
            
            # 按操作类型统计
            create_count = sum(1 for r in sync_records if r.operation == SyncOperation.CREATE)
            update_count = sum(1 for r in sync_records if r.operation == SyncOperation.UPDATE)
            
            self.logger.info(f"   需要创建: {create_count} 条")
            self.logger.info(f"   需要更新: {update_count} 条")
            
            if self.config.dry_run:
                self.logger.info("🧪 演练模式，不会实际修改数据")
                result.created_count = create_count
                result.updated_count = update_count
                return result
            
            # 2. 分批处理同步
            batches = self._create_batches(sync_records)
            
            for i, batch in enumerate(batches, 1):
                self.logger.info(f"📦 处理批次 {i}/{len(batches)}: {len(batch)} 条记录")
                
                batch_result = await self._process_batch(batch)
                
                # 合并结果
                result.created_count += batch_result.created_count
                result.updated_count += batch_result.updated_count
                result.skipped_count += batch_result.skipped_count
                result.error_count += batch_result.error_count
                result.errors.extend(batch_result.errors)
                
                # 批次间延迟
                if i < len(batches):
                    await asyncio.sleep(self.config.sync_retry_delay)
            
            result.processing_time = time.time() - start_time
            
            self.logger.info("✅ 数据同步完成!")
            self.logger.info(f"📊 结果: 创建={result.created_count}, 更新={result.updated_count}, "
                           f"跳过={result.skipped_count}, 错误={result.error_count}")
            self.logger.info(f"⏱️  用时: {result.processing_time:.1f}秒")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ 数据同步失败: {e}")
            result.processing_time = time.time() - start_time
            result.errors.append(f"同步过程异常: {str(e)}")
            raise
    
    async def _analyze_sync_needs(self) -> List[SyncRecord]:
        """分析同步需求"""
        self.logger.info(f"🔍 分析同步需求 (模式: {self.config.sync_mode})...")
        
        if self.config.sync_mode == "update_all":
            return await self._analyze_update_all_needs()
        elif self.config.sync_mode == "priority_new":
            return await self._analyze_priority_new_needs()
        else:
            return await self._analyze_missing_only_needs()
    
    async def _analyze_missing_only_needs(self) -> List[SyncRecord]:
        """分析缺失记录的同步需求"""
        # 获取所有有效的提交记录
        # 注意：需要从x_linked_to URL中提取纯tweet ID来与campaign_tweet_snapshot.tweet_id匹配
        query = """
        SELECT DISTINCT
            cts.x_linked_to as target_tweet_url,
            SUBSTRING_INDEX(SUBSTRING_INDEX(cts.x_linked_to, '/status/', -1), '?', 1) as target_tweet_id,
            cts.id,
            cts.task_id,
            cts.submitter_uid,
            cts.x_type,
            cts.x_tweet_id,
            cts.is_valid,
            cts.view_count,
            cts.reward_amount,
            cts.status,
            cts.created_at,
            cts.is_del,
            cts.updated_at,
            cts.yaps,
            cst.tweet_id as existing_tweet_id,
            cst.views as existing_views
        FROM campaign_task_submission cts
        LEFT JOIN campaign_tweet_snapshot cst ON SUBSTRING_INDEX(SUBSTRING_INDEX(cts.x_linked_to, '/status/', -1), '?', 1) = cst.tweet_id
        WHERE cts.x_linked_to IS NOT NULL 
        AND cts.x_linked_to != ''
        AND cts.is_del = 0
        ORDER BY cts.x_linked_to, cts.created_at DESC
        """
        
        # 使用统一的数据库连接方法
        connection = await self._get_database_connection()
        cursor = await connection.cursor(aiomysql.DictCursor)
        await cursor.execute(query)
        records = await cursor.fetchall()
        await cursor.close()
        connection.close()
        
        # 分析每条记录的同步需求
        sync_records = []
        processed_tweets = set()  # 避免重复处理同一个推文ID
        
        for record in records:
            target_tweet_id = record['target_tweet_id']  # 这是从URL提取的纯tweet ID
            target_tweet_url = record['target_tweet_url']  # 这是完整的URL
            
            # 跳过已处理的目标推文ID（每个目标推文ID只处理一次）
            if target_tweet_id in processed_tweets:
                continue
            
            processed_tweets.add(target_tweet_id)
            
            # 创建TaskSubmission对象
            submission = TaskSubmission(
                id=record['id'],
                task_id=record['task_id'],
                submitter_uid=record['submitter_uid'],
                x_tweet_id=record['x_tweet_id'],  # 用户自己的推文ID
                x_type=record['x_type'],
                x_linked_to=target_tweet_url,  # 目标推文完整URL
                is_valid=record['is_valid'],
                view_count=record['view_count'],
                reward_amount=float(record['reward_amount']) if record['reward_amount'] else None,
                status=record['status'],
                created_at=record['created_at'],
                is_del=record['is_del'],
                updated_at=record['updated_at'],
                yaps=record['yaps']
            )
            
            # 判断同步操作类型 - 基于目标推文ID
            if not record['existing_tweet_id']:
                # 需要创建新记录 - 为目标推文创建snapshot
                sync_record = SyncRecord(
                    tweet_id=target_tweet_id,  # 使用目标推文ID
                    operation=SyncOperation.CREATE,
                    submission_data=submission,
                    reason="缺失目标推文快照记录"
                )
                sync_records.append(sync_record)
                
            elif record['existing_views'] != record['view_count']:
                # 需要更新现有记录
                sync_record = SyncRecord(
                    tweet_id=target_tweet_id,  # 使用目标推文ID
                    operation=SyncOperation.UPDATE,
                    submission_data=submission,
                    reason=f"views不一致: {record['existing_views']} -> {record['view_count']}"
                )
                sync_records.append(sync_record)
            
            # 如果数据一致则跳过
        
        self.logger.info(f"🔍 分析完成: 需要处理 {len(sync_records)} 条记录")
        return sync_records
    
    async def _analyze_update_all_needs(self) -> List[SyncRecord]:
        """分析全部更新需求 - 更新所有现有记录的Twitter数据"""
        # 获取所有campaign_tweet_snapshot中的记录
        query = """
        SELECT 
            tweet_id,
            author_username,
            views,
            created_at
        FROM campaign_tweet_snapshot
        WHERE tweet_id IS NOT NULL 
        AND tweet_id != ''
        ORDER BY id DESC
        """
        
        # 使用原始查询
        connection = await self._get_database_connection()
        
        cursor = await connection.cursor(aiomysql.DictCursor)
        await cursor.execute(query)
        records = await cursor.fetchall()
        await cursor.close()
        connection.close()
        
        # 为每条现有记录创建更新任务
        sync_records = []
        for record in records:
            # 创建一个虚拟的TaskSubmission来兼容现有逻辑
            submission = TaskSubmission(
                id=0,  # 虚拟ID
                task_id=0,
                submitter_uid=0,
                x_tweet_id=record['tweet_id'],
                x_type='refresh',  # 标记为刷新操作
                x_linked_to=None,
                is_valid=1,
                view_count=None,  # 不使用旧的view_count，完全从Twitter获取
                reward_amount=None,
                status='refresh',
                created_at=record['created_at'],
                is_del=0,
                updated_at=record['created_at'],  # 使用created_at替代
                yaps=None
            )
            
            sync_record = SyncRecord(
                tweet_id=record['tweet_id'],
                operation=SyncOperation.UPDATE,
                submission_data=submission,
                reason=f"全部更新模式 - 刷新Twitter数据"
            )
            sync_records.append(sync_record)
        
        self.logger.info(f"🔄 全部更新模式: 找到 {len(sync_records)} 条现有记录需要刷新")
        return sync_records
    
    async def _analyze_priority_new_needs(self) -> List[SyncRecord]:
        """分析优先级同步需求 - 专门处理从未同步过的数据"""
        # 查找在campaign_task_submission中但不在campaign_tweet_snapshot中的记录
        query = """
        SELECT DISTINCT
            cts.x_linked_to as target_tweet_url,
            SUBSTRING_INDEX(SUBSTRING_INDEX(cts.x_linked_to, '/status/', -1), '?', 1) as target_tweet_id,
            cts.id,
            cts.task_id,
            cts.submitter_uid,
            cts.x_type,
            cts.x_tweet_id,
            cts.is_valid,
            cts.view_count,
            cts.reward_amount,
            cts.status,
            cts.created_at,
            cts.is_del,
            cts.updated_at,
            cts.yaps
        FROM campaign_task_submission cts
        LEFT JOIN campaign_tweet_snapshot cst ON SUBSTRING_INDEX(SUBSTRING_INDEX(cts.x_linked_to, '/status/', -1), '?', 1) = cst.tweet_id
        WHERE cts.x_linked_to IS NOT NULL 
        AND cts.x_linked_to != ''
        AND cts.is_del = 0
        AND cts.is_valid = 1
        AND cst.tweet_id IS NULL  -- 关键条件：在campaign_tweet_snapshot中不存在
        ORDER BY cts.created_at ASC  -- 按时间升序，优先处理早期数据
        """
        
        # 使用原始查询
        connection = await self._get_database_connection()
        
        cursor = await connection.cursor(aiomysql.DictCursor)
        await cursor.execute(query)
        records = await cursor.fetchall()
        await cursor.close()
        connection.close()
        
        # 分析每条记录的同步需求
        sync_records = []
        processed_tweets = set()  # 避免重复处理同一个推文ID
        
        for record in records:
            target_tweet_id = record['target_tweet_id']  # 这是从URL提取的纯tweet ID
            target_tweet_url = record['target_tweet_url']  # 这是完整的URL
            
            # 跳过已处理的目标推文ID（每个目标推文ID只处理一次）
            if target_tweet_id in processed_tweets:
                continue
            
            processed_tweets.add(target_tweet_id)
            
            # 创建TaskSubmission对象
            submission = TaskSubmission(
                id=record['id'],
                task_id=record['task_id'],
                submitter_uid=record['submitter_uid'],
                x_tweet_id=record['x_tweet_id'],  # 用户自己的推文ID
                x_type=record['x_type'],
                x_linked_to=target_tweet_url,  # 目标推文完整URL
                is_valid=record['is_valid'],
                view_count=record['view_count'],
                reward_amount=float(record['reward_amount']) if record['reward_amount'] else None,
                status=record['status'],
                created_at=record['created_at'],
                is_del=record['is_del'],
                updated_at=record['updated_at'],
                yaps=record['yaps']
            )
            
            # 所有优先级记录都是需要新创建的
            sync_record = SyncRecord(
                tweet_id=target_tweet_id,  # 使用目标推文ID
                operation=SyncOperation.CREATE,
                submission_data=submission,
                reason="优先级同步 - 从未同步过的目标推文"
            )
            sync_records.append(sync_record)
        
        self.logger.info(f"⚡ 优先级同步: 找到 {len(sync_records)} 条从未同步过的记录")
        return sync_records
    
    def _create_batches(self, sync_records: List[SyncRecord]) -> List[List[SyncRecord]]:
        """创建批次"""
        batches = []
        for i in range(0, len(sync_records), self.config.sync_batch_size):
            batch = sync_records[i:i + self.config.sync_batch_size]
            batches.append(batch)
        return batches
    
    async def _process_batch(self, batch: List[SyncRecord]) -> SyncResult:
        """处理单个批次"""
        result = SyncResult()
        
        for sync_record in batch:
            try:
                if sync_record.operation == SyncOperation.CREATE:
                    create_result = await self._create_snapshot_record(sync_record.submission_data)
                    if create_result == "success":
                        result.created_count += 1
                        self.logger.debug(f"✅ 创建记录: {sync_record.tweet_id}")
                    elif create_result == "skipped":
                        result.skipped_count += 1
                        self.logger.debug(f"⏭️  跳过记录: {sync_record.tweet_id} (推文不存在)")
                    else:
                        result.error_count += 1
                        result.errors.append(f"创建失败: {sync_record.tweet_id}")
                
                elif sync_record.operation == SyncOperation.UPDATE:
                    update_result = await self._update_snapshot_record(sync_record.submission_data)
                    if update_result == "success":
                        result.updated_count += 1
                        self.logger.debug(f"✅ 更新记录: {sync_record.tweet_id}")
                    elif update_result == "skipped":
                        result.skipped_count += 1
                        self.logger.debug(f"⏭️  跳过记录: {sync_record.tweet_id} (推文不存在)")
                    else:
                        result.error_count += 1
                        result.errors.append(f"更新失败: {sync_record.tweet_id}")
                
            except Exception as e:
                result.error_count += 1
                error_msg = f"处理 {sync_record.tweet_id} 失败: {str(e)}"
                result.errors.append(error_msg)
                self.logger.error(f"❌ {error_msg}")
        
        return result
    
    async def _create_snapshot_record(self, submission: TaskSubmission) -> str:
        """
        创建快照记录 - 智能错误处理确保技术错误不影响帖子状态
        
        Args:
            submission: 任务提交记录
            
        Returns:
            str: 处理结果
                - 'success': 成功创建
                - 'skipped': 跳过处理（可能是技术问题或内容问题）
                - 'failed': 处理失败
                
        处理逻辑:
            1. 技术错误（网络、服务器、浏览器等）-> 跳过但不标记帖子无效
            2. 内容错误（推文删除、私密等）-> 跳过并标记帖子无效
            3. 风控错误 -> 等待重试
        """
        try:
            # 必须先获取完整的Twitter数据 - 使用目标推文ID(x_linked_to)
            twitter_data = None
            if self.config.enable_twitter_api:
                try:
                    twitter_data = await self._get_comprehensive_twitter_data(submission.x_linked_to)
                except Exception as e:
                    # 检查是否是风控导致的异常
                    if (hasattr(e, 'wait_time') and 
                        type(e).__name__ == 'RateLimitDetectedError'):
                        self.logger.warning(f"🚨 创建记录时检测到风控，已在获取数据时处理等待: {submission.x_linked_to}")
                        # 风控已经在_get_comprehensive_twitter_data中处理了，这里再试一次
                        try:
                            twitter_data = await self._get_comprehensive_twitter_data(submission.x_linked_to)
                        except Exception as retry_e:
                            self.logger.error(f"❌ 风控处理后重试仍失败 {submission.x_linked_to}: {retry_e}")
                            return "failed"
                    else:
                        self.logger.error(f"❌ 获取Twitter数据失败 {submission.x_linked_to}: {e}")
                        return "failed"
            
            # === 智能错误处理：区分技术错误和内容错误 ===
            if not twitter_data:
                # 数据为空可能的原因：
                # 1. 网络问题、服务器错误 -> 技术错误，不影响帖子状态
                # 2. 推文真的被删除 -> 内容错误，需要标记无效
                analysis = error_handler.analyze_error(
                    Exception("数据提取为空"), 
                    "", 
                    "data_empty"
                )
                error_handler.log_error_analysis(analysis, submission.x_linked_to)
                
                # 只有确认是内容问题才标记帖子无效
                if error_handler.should_mark_submission_invalid(analysis):
                    await self._mark_submission_invalid(submission.x_linked_to)
                
                return error_handler.get_return_status(analysis)
            
            # 检查是否确认推文已删除
            if isinstance(twitter_data, dict) and twitter_data.get('tweet_deleted'):
                analysis = error_handler.analyze_error(
                    Exception("推文不存在"), 
                    f"推文状态: {twitter_data.get('reason')}", 
                    twitter_data.get('reason', 'tweet_deleted')
                )
                error_handler.log_error_analysis(analysis, submission.x_linked_to)
                
                if error_handler.should_mark_submission_invalid(analysis):
                    await self._mark_submission_invalid(submission.x_linked_to)
                
                return error_handler.get_return_status(analysis)
            
            # 使用完整的Twitter数据创建记录
            # 从URL中提取纯tweet ID用于数据库存储
            pure_tweet_id = self._extract_tweet_id_from_url(submission.x_linked_to)
            
            snapshot = CampaignTweetSnapshot(
                tweet_id=pure_tweet_id,  # 使用提取的纯tweet ID
                tweet_type=submission.x_type,
                success=True,
                message="从campaign_task_submission同步创建（含完整Twitter数据）",
                
                # Twitter API获取的完整数据
                author_username=twitter_data.get('author_username', 'unknown'),
                author_name=twitter_data.get('author_name'),
                author_avatar=twitter_data.get('author_avatar'),
                author_verified=twitter_data.get('author_verified', False),
                
                tweet_text=twitter_data.get('tweet_text'),
                tweet_time_utc=twitter_data.get('tweet_time_utc'),
                
                # 推文统计数据 - 优先使用submission的view_count
                views=submission.view_count if submission.view_count else twitter_data.get('views'),
                replies=twitter_data.get('replies'),
                retweets=twitter_data.get('retweets'),  
                likes=twitter_data.get('likes'),
                quotes=twitter_data.get('quotes'),
                
                # 汇总信息
                summary_total_tweets=twitter_data.get('summary_total_tweets'),
                summary_has_thread=twitter_data.get('summary_has_thread'),
                summary_has_replies=twitter_data.get('summary_has_replies'),
                
                # JSON结构数据
                primary_tweet=twitter_data.get('primary_tweet'),
                thread=twitter_data.get('thread'),
                related=twitter_data.get('related')
            )
            
            # 插入数据库
            success = await self.db_service.create_record(snapshot)
            if success:
                self.logger.debug(f"✅ 成功创建完整记录: {submission.x_linked_to}, author: {twitter_data.get('author_username')}, views: {snapshot.views}")
                return "success"
            else:
                return "failed"
            
        except Exception as e:
            self.logger.error(f"❌ 创建快照记录失败 {submission.x_linked_to}: {e}")
            return "failed"
    
    async def _update_snapshot_record(self, submission: TaskSubmission) -> str:
        """
        更新快照记录 - 智能错误处理确保技术错误不影响帖子状态
        
        Args:
            submission: 任务提交记录
            
        Returns:
            str: 处理结果
                - 'success': 成功更新
                - 'skipped': 跳过处理（技术问题保留原状态，内容问题标记无效）
                - 'failed': 处理失败
                
        处理逻辑:
            1. 优先从Twitter API获取最新数据
            2. API失败时fallback到submission数据
            3. 技术错误不影响帖子状态，内容错误标记无效
        """
        try:
            # 获取现有记录 - 使用从URL提取的纯tweet ID查找
            pure_tweet_id = self._extract_tweet_id_from_url(submission.x_linked_to)
            existing = await self.db_service.get_by_tweet_id(pure_tweet_id)
            if not existing:
                self.logger.warning(f"⚠️  找不到要更新的记录: {pure_tweet_id} (来源URL: {submission.x_linked_to})")
                return "failed"
            
            # 如果启用Twitter API，获取最新数据 - 使用目标推文ID(x_linked_to)
            if self.config.enable_twitter_api:
                try:
                    twitter_data = await self._get_comprehensive_twitter_data(submission.x_linked_to)
                    if twitter_data:
                        # 更新所有可用字段
                        existing.author_username = twitter_data.get('author_username', existing.author_username)
                        existing.author_name = twitter_data.get('author_name') or existing.author_name
                        existing.author_avatar = twitter_data.get('author_avatar') or existing.author_avatar
                        existing.author_verified = twitter_data.get('author_verified', existing.author_verified)
                        
                        existing.tweet_text = twitter_data.get('tweet_text') or existing.tweet_text
                        existing.tweet_time_utc = twitter_data.get('tweet_time_utc') or existing.tweet_time_utc
                        
                        # 更新统计数据 - 这些是最重要的
                        existing.views = twitter_data.get('views') or existing.views
                        existing.replies = twitter_data.get('replies') or existing.replies
                        existing.retweets = twitter_data.get('retweets') or existing.retweets
                        existing.likes = twitter_data.get('likes') or existing.likes
                        existing.quotes = twitter_data.get('quotes') or existing.quotes
                        
                        # 更新汇总信息
                        existing.summary_total_tweets = twitter_data.get('summary_total_tweets') or existing.summary_total_tweets
                        existing.summary_has_thread = twitter_data.get('summary_has_thread')
                        existing.summary_has_replies = twitter_data.get('summary_has_replies')
                        
                        # 更新JSON数据
                        existing.primary_tweet = twitter_data.get('primary_tweet') or existing.primary_tweet
                        existing.thread = twitter_data.get('thread') or existing.thread
                        existing.related = twitter_data.get('related') or existing.related
                        
                        existing.message = "数据已从Twitter API刷新"
                        self.logger.debug(f"✅ 从Twitter更新数据: {submission.x_linked_to}, views: {existing.views}")
                    else:
                        # 使用错误处理器分析数据获取结果
                        if isinstance(twitter_data, dict) and twitter_data.get('tweet_deleted'):
                            analysis = error_handler.analyze_error(
                                Exception("推文不存在"), 
                                f"推文状态: {twitter_data.get('reason')}", 
                                twitter_data.get('reason', 'tweet_deleted')
                            )
                        else:
                            analysis = error_handler.analyze_error(
                                Exception("数据提取为空"), 
                                "", 
                                "data_empty_update"
                            )
                        
                        error_handler.log_error_analysis(analysis, submission.x_linked_to)
                        
                        if error_handler.should_mark_submission_invalid(analysis):
                            await self._mark_submission_invalid(submission.x_linked_to)
                        
                        return error_handler.get_return_status(analysis)
                        
                except Exception as e:
                    self.logger.warning(f"⚠️  Twitter API调用失败，使用submission数据: {submission.x_linked_to}: {e}")
                    # fallback 到 submission 数据
                    if submission.view_count is not None:
                        existing.views = submission.view_count
                    existing.tweet_type = submission.x_type
                    existing.message = "部分数据更新（Twitter API异常）"
            else:
                # 不使用Twitter API时，只更新submission提供的数据
                if submission.view_count is not None:
                    existing.views = submission.view_count
                existing.tweet_type = submission.x_type
                existing.message = "数据更新（未使用Twitter API）"
            
            # 注意：表中没有updated_at字段，数据库会自动管理时间戳
            
            # 更新数据库
            success = await self.db_service.update_record(existing)
            if success:
                return "success"
            else:
                return "failed"
            
        except Exception as e:
            self.logger.error(f"❌ 更新快照记录失败 {submission.x_linked_to}: {e}")
            return "failed"
    
    def _parse_twitter_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """解析Twitter时间戳为datetime对象"""
        if not timestamp_str:
            return None
        
        try:
            from datetime import datetime
            # Twitter API返回格式: '2025-08-07T22:48:55.000Z'
            if timestamp_str.endswith('Z'):
                # 移除毫秒和Z，然后解析
                timestamp_str = timestamp_str.replace('.000Z', '').replace('Z', '')
                return datetime.fromisoformat(timestamp_str)
            elif 'T' in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            self.logger.warning(f"⚠️  时间戳解析失败: {timestamp_str}, 错误: {e}")
            return None

    def _extract_tweet_id_from_url(self, tweet_url: str) -> str:
        """从推文URL中提取纯tweet ID"""
        try:
            # 支持多种URL格式:
            # https://x.com/username/status/1234567890
            # https://twitter.com/username/status/1234567890
            import re
            pattern = r'/status/(\d+)'
            match = re.search(pattern, tweet_url)
            if match:
                return match.group(1)
            else:
                # 如果没有匹配到，返回原始URL（向后兼容）
                self.logger.warning(f"⚠️  无法从URL提取tweet ID: {tweet_url}")
                return tweet_url
        except Exception as e:
            self.logger.error(f"❌ 提取tweet ID失败: {tweet_url}, 错误: {e}")
            return tweet_url
    
    async def _get_comprehensive_twitter_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """获取完整推文数据"""
        try:
            # tweet_url 已经是完整的URL，不需要拼接
            # 例如: https://x.com/username/status/1234567890
            
            # 获取Twitter服务实例
            twitter_service = await self._get_twitter_service()
            
            # 调用综合数据接口获取完整信息
            comprehensive_data = await twitter_service.get_comprehensive_data(tweet_url)
            
            if not comprehensive_data:
                self.logger.warning(f"⚠️  Twitter API返回失败: {tweet_url}")
                return None
            
            # 兼容新的数据结构：直接从根级别获取primary_tweet
            primary_tweet = comprehensive_data.get('primary_tweet', {})
            
            if not primary_tweet:
                # 检查是否有提取元数据中的错误信息
                extraction_metadata = comprehensive_data.get('extraction_metadata', {})
                error_msg = extraction_metadata.get('error', '')
                detailed_reason = extraction_metadata.get('detailed_reason', '')
                
                # 使用错误处理器进行智能分析
                analysis = error_handler.analyze_error(
                    Exception(error_msg or "数据提取失败"),
                    error_msg,
                    detailed_reason,
                    extraction_metadata
                )
                
                error_handler.log_error_analysis(analysis, tweet_url)
                
                # 根据分析结果决定返回值
                if analysis.category == ErrorCategory.CONTENT_ERROR:
                    # 内容问题：推文确实不存在
                    return {'tweet_deleted': True, 'reason': detailed_reason}
                elif analysis.category == ErrorCategory.RATE_LIMIT:
                    # 风控问题：抛出特定异常
                    class RateLimitDetectedError(Exception):
                        def __init__(self, message: str, wait_time: int = 300):
                            super().__init__(message)
                            self.wait_time = wait_time
                    raise RateLimitDetectedError(f"检测到Twitter风控: {error_msg}", wait_time=analysis.wait_time or 300)
                else:
                    # 技术问题：返回None，不影响帖子状态
                    return None
            
            # 解析并返回结构化数据 - 适配新的Twitter服务数据结构
            author = primary_tweet.get('author', {})
            metrics = primary_tweet.get('metrics', {})
            
            return {
                # 作者信息
                'author_username': author.get('username', 'unknown'),
                'author_name': author.get('display_name'),
                'author_avatar': author.get('avatar_url'),
                'author_verified': bool(author.get('is_verified', False)),
                
                # 推文内容
                'tweet_text': primary_tweet.get('text'),
                'tweet_time_utc': self._parse_twitter_timestamp(primary_tweet.get('timestamp')),
                
                # 统计数据
                'views': metrics.get('views'),
                'replies': metrics.get('replies'),
                'retweets': metrics.get('retweets'),
                'likes': metrics.get('likes'),
                'quotes': metrics.get('quotes'),
                
                # 汇总信息
                'summary_total_tweets': comprehensive_data.get('extraction_metadata', {}).get('total_tweets_found'),
                'summary_has_thread': bool(comprehensive_data.get('thread_tweets', [])),
                'summary_has_replies': bool(comprehensive_data.get('related_tweets', [])),
                
                # 原始JSON数据
                'primary_tweet': primary_tweet,
                'thread': comprehensive_data.get('thread_tweets'),
                'related': comprehensive_data.get('related_tweets')
            }
            
        except Exception as e:
            # 检查是否是风控异常（检查异常名称和属性）
            if (hasattr(e, 'wait_time') and 
                type(e).__name__ == 'RateLimitDetectedError'):
                self.logger.warning(f"🚨 检测到风控，等待 {e.wait_time} 秒后重试: {tweet_url}")
                # 等待指定时间
                await asyncio.sleep(e.wait_time)
                # 重试一次
                try:
                    self.logger.info(f"🔄 风控等待完成，重试获取: {tweet_url}")
                    twitter_service = await self._get_twitter_service()
                    comprehensive_data = await twitter_service.get_comprehensive_data(tweet_url)
                    
                    if not comprehensive_data:
                        self.logger.warning(f"⚠️  重试后仍无法获取数据: {tweet_url}")
                        return None
                        
                    # 重新解析数据（重复上面的逻辑）
                    primary_tweet = comprehensive_data.get('primary_tweet', {})
                    if not primary_tweet:
                        # 重试后也检查错误类型
                        extraction_metadata = comprehensive_data.get('extraction_metadata', {})
                        error_msg = extraction_metadata.get('error', '')
                        detailed_reason = extraction_metadata.get('detailed_reason', '')
                        
                        # 根据详细原因分类处理
                        if detailed_reason in ['rate_limited', 'login_required', 'page_load_error', 'network_error']:
                            self.logger.error(f"❌ 技术错误 - 重试后仍为{detailed_reason}: {tweet_url}")
                            return None  # 技术问题
                        elif detailed_reason in ['tweet_not_found', 'tweet_protected']:
                            self.logger.warning(f"⚠️  重试确认推文状态 - {detailed_reason}: {tweet_url}")
                        elif '超时' in error_msg or 'timeout' in error_msg.lower():
                            self.logger.error(f"❌ 技术错误 - 重试后获取推文仍超时: {tweet_url} - {error_msg}")
                            return None  # 超时问题
                        elif '实例' in error_msg or 'instance' in error_msg.lower():
                            self.logger.error(f"❌ 技术错误 - 重试后浏览器实例仍有问题: {tweet_url} - {error_msg}")
                            return None  # 实例问题
                        else:
                            self.logger.warning(f"⚠️  重试后未找到主推文数据: {tweet_url} (原因: {detailed_reason or error_msg})")
                        return None
                    
                    # 返回解析的数据
                    author = primary_tweet.get('author', {})
                    metrics = primary_tweet.get('metrics', {})
                    
                    return {
                        'author_username': author.get('username', 'unknown'),
                        'author_name': author.get('display_name'),
                        'author_avatar': author.get('avatar_url'),
                        'author_verified': bool(author.get('is_verified', False)),
                        'tweet_text': primary_tweet.get('text'),
                        'tweet_time_utc': self._parse_twitter_timestamp(primary_tweet.get('timestamp')),
                        'views': metrics.get('views'),
                        'replies': metrics.get('replies'),
                        'retweets': metrics.get('retweets'),
                        'likes': metrics.get('likes'),
                        'quotes': metrics.get('quotes'),
                        'summary_total_tweets': comprehensive_data.get('extraction_metadata', {}).get('total_tweets_found'),
                        'summary_has_thread': bool(comprehensive_data.get('thread_tweets', [])),
                        'summary_has_replies': bool(comprehensive_data.get('related_tweets', [])),
                        'primary_tweet': primary_tweet,
                        'thread': comprehensive_data.get('thread_tweets'),
                        'related': comprehensive_data.get('related_tweets')
                    }
                except Exception as retry_error:
                    self.logger.error(f"❌ 风控等待后重试仍失败 {tweet_url}: {retry_error}")
                    return None
            else:
                self.logger.error(f"❌ 获取推文完整数据失败 {tweet_url}: {e}")
                return None
    
    async def _mark_submission_invalid(self, target_tweet_id: str) -> bool:
        """将campaign_task_submission中的推文记录标记为无效 - 基于x_linked_to字段"""
        try:
            # 使用原始SQL更新is_valid字段
            connection = await self._get_database_connection()
            
            cursor = await connection.cursor()
            
            # 更新所有匹配的记录为无效 - 基于x_linked_to字段
            update_query = """
            UPDATE campaign_task_submission 
            SET is_valid = 0 
            WHERE x_linked_to = %s AND is_valid = 1
            """
            
            result = await cursor.execute(update_query, (target_tweet_id,))
            await connection.commit()
            
            if cursor.rowcount > 0:
                self.logger.info(f"✅ 标记 {cursor.rowcount} 条submission记录为无效(基于x_linked_to): {target_tweet_id}")
                success = True
            else:
                self.logger.debug(f"📝 没有找到需要更新的submission记录(基于x_linked_to): {target_tweet_id}")
                success = True  # 不算错误
            
            await cursor.close()
            connection.close()
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ 标记submission为无效失败(基于x_linked_to) {target_tweet_id}: {e}")
            return False
    
    async def _get_twitter_service(self):
        """获取Twitter服务实例 - 单例模式避免重复创建"""
        if self._twitter_service is None:
            # 使用现有的独立Twitter服务创建函数
            from ..data_updater.service import _create_standalone_twitter_service
            self._twitter_service = await _create_standalone_twitter_service()
        return self._twitter_service
    
    async def cleanup(self):
        """清理服务资源"""
        if self._twitter_service:
            try:
                # 使用Twitter服务的cleanup方法
                if hasattr(self._twitter_service, 'cleanup'):
                    await self._twitter_service.cleanup()
                else:
                    # 兼容旧版本：直接清理数据管理器中的资源
                    if hasattr(self._twitter_service, 'data_manager'):
                        for source in self._twitter_service.data_manager.sources:
                            if hasattr(source, 'cleanup'):
                                if inspect.iscoroutinefunction(source.cleanup):
                                    await source.cleanup()
                                else:
                                    source.cleanup()
                self.logger.info("✅ Twitter服务资源清理完成")
            except Exception as e:
                self.logger.error(f"❌ Twitter服务清理失败: {e}")
            finally:
                self._twitter_service = None
    
    def get_sync_statistics(self) -> Dict[str, Any]:
        """获取同步统计信息"""
        return {
            'config': {
                'sync_batch_size': self.config.sync_batch_size,
                'max_concurrent_syncs': self.config.max_concurrent_syncs,
                'skip_invalid_records': self.config.skip_invalid_records,
                'mark_invalid_on_error': self.config.mark_invalid_on_error
            },
            'service_status': 'ready'
        }