"""
数据更新服务

遵循SOLID原则的核心数据更新服务
负责协调数据库查询、Twitter API调用、批处理管理和进度追踪
专为732条记录的高效更新设计
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass

from ..database import DatabaseService, CampaignTweetSnapshot, CampaignTweetSnapshotQuery
from ..twitter.service import TwitterService
from ...core.config_factory import get_updater_config, UpdaterConfig
from .batch_manager import BatchManager, BatchInfo, BatchResult, BatchStrategy
from .rate_limiter import BatchRateLimiter
from .progress_tracker import ProgressTracker, UpdateStatus, RecordProgress


@dataclass
class UpdateResult:
    """更新结果数据类"""
    total_records: int
    processed_records: int
    successful_updates: int
    failed_updates: int
    skipped_records: int
    processing_time: float
    success_rate: float
    errors: List[str]
    session_id: str


class TweetDataUpdater:
    """推文数据更新器 - 单一职责原则"""
    
    def __init__(self, 
                 database_service: DatabaseService,
                 twitter_service: TwitterService,
                 config: UpdaterConfig = None):
        """
        初始化推文数据更新器
        
        Args:
            database_service: 数据库服务
            twitter_service: Twitter服务
            config: 更新配置
        """
        self.db_service = database_service
        self.twitter_service = twitter_service
        self.config = config or get_updater_config('safe')
        
        # 验证配置
        is_valid, error_msg = self.config.validate()
        if not is_valid:
            raise ValueError(f"配置无效: {error_msg}")
        
        self.logger = logging.getLogger(__name__)
        
        # 核心组件
        self.rate_limiter = BatchRateLimiter(
            requests_per_minute=self.config.requests_per_minute,
            requests_per_hour=self.config.requests_per_hour,
            base_delay=self.config.request_delay_seconds,
            batch_delay=self.config.batch_delay_seconds
        )
        
        self.batch_manager = BatchManager(
            config=self.config,
            rate_limiter=self.rate_limiter
        )
        
        self.progress_tracker: Optional[ProgressTracker] = None
        
        self.logger.info("数据更新器初始化完成")
        self.logger.info(f"配置: {self.config}")
    
    async def update_all_records(self, 
                               filter_recent: bool = None,
                               batch_strategy: str = "equal",
                               progress_file: str = None) -> UpdateResult:
        """
        更新所有需要更新的记录
        
        Args:
            filter_recent: 是否过滤最近已更新的记录
            batch_strategy: 批处理策略 ("equal", "priority", "adaptive")
            progress_file: 进度文件路径
            
        Returns:
            更新结果
        """
        start_time = time.time()
        
        # 初始化进度追踪
        session_id = f"update_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.progress_tracker = ProgressTracker(
            session_id=session_id,
            progress_file_path=progress_file or f"progress/{session_id}.json",
            auto_save_interval=self.config.progress_save_interval
        )
        
        try:
            self.logger.info("开始全量数据更新...")
            
            # 第1步: 获取需要更新的记录
            self.progress_tracker.update_phase("查询需要更新的记录")
            
            if filter_recent is None:
                filter_recent = self.config.skip_recent_updates
            
            records_to_update = await self._get_records_to_update(filter_recent)
            
            if not records_to_update:
                self.logger.info("没有需要更新的记录")
                return UpdateResult(
                    total_records=0,
                    processed_records=0,
                    successful_updates=0,
                    failed_updates=0,
                    skipped_records=0,
                    processing_time=time.time() - start_time,
                    success_rate=100.0,
                    errors=[],
                    session_id=session_id
                )
            
            self.logger.info(f"找到 {len(records_to_update)} 条需要更新的记录")
            
            # 第2步: 创建批次
            self.progress_tracker.update_phase("创建处理批次")
            
            batches = self.batch_manager.create_batches(
                records=records_to_update,
                strategy=batch_strategy
            )
            
            # 初始化进度追踪会话
            self.progress_tracker.initialize_session(
                total_records=len(records_to_update),
                total_batches=len(batches)
            )
            
            # 第3步: 处理批次
            self.progress_tracker.update_phase("批量处理数据")
            
            batch_results = await self.batch_manager.process_batches(
                batches=batches,
                batch_processor=self._process_batch,
                progress_callback=self._on_batch_complete
            )
            
            # 第4步: 汇总结果
            result = self._create_update_result(
                records_to_update=records_to_update,
                batch_results=batch_results,
                processing_time=time.time() - start_time,
                session_id=session_id
            )
            
            # 完成会话
            final_status = UpdateStatus.COMPLETED if result.success_rate > 50 else UpdateStatus.FAILED
            self.progress_tracker.complete_session(final_status)
            
            self.logger.info("全量数据更新完成")
            self.logger.info(f"最终结果: {result.successful_updates}/{result.total_records} 成功 "
                           f"({result.success_rate:.1f}%)")
            
            return result
            
        except Exception as e:
            self.logger.error(f"数据更新过程异常: {e}")
            if self.progress_tracker:
                self.progress_tracker.complete_session(UpdateStatus.FAILED)
            raise
    
    async def update_specific_records(self, 
                                    record_ids: List[int],
                                    progress_file: str = None) -> UpdateResult:
        """
        更新指定的记录
        
        Args:
            record_ids: 要更新的记录ID列表
            progress_file: 进度文件路径
            
        Returns:
            更新结果
        """
        start_time = time.time()
        
        # 初始化进度追踪
        session_id = f"update_specific_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.progress_tracker = ProgressTracker(
            session_id=session_id,
            progress_file_path=progress_file or f"progress/{session_id}.json",
            auto_save_interval=self.config.progress_save_interval
        )
        
        try:
            self.logger.info(f"开始更新指定记录: {len(record_ids)} 条")
            
            # 获取记录
            self.progress_tracker.update_phase("查询指定记录")
            
            records = []
            for record_id in record_ids:
                record = await self.db_service.get_by_id(record_id)
                if record:
                    records.append(record)
                else:
                    self.logger.warning(f"记录 {record_id} 未找到")
            
            if not records:
                self.logger.warning("没有找到有效的记录")
                return UpdateResult(
                    total_records=len(record_ids),
                    processed_records=0,
                    successful_updates=0,
                    failed_updates=0,
                    skipped_records=len(record_ids),
                    processing_time=time.time() - start_time,
                    success_rate=0.0,
                    errors=["没有找到有效记录"],
                    session_id=session_id
                )
            
            # 创建批次并处理
            batches = self.batch_manager.create_batches(records, "equal")
            self.progress_tracker.initialize_session(len(records), len(batches))
            
            batch_results = await self.batch_manager.process_batches(
                batches=batches,
                batch_processor=self._process_batch,
                progress_callback=self._on_batch_complete
            )
            
            # 汇总结果
            result = self._create_update_result(
                records_to_update=records,
                batch_results=batch_results,
                processing_time=time.time() - start_time,
                session_id=session_id
            )
            
            final_status = UpdateStatus.COMPLETED if result.success_rate > 50 else UpdateStatus.FAILED
            self.progress_tracker.complete_session(final_status)
            
            return result
            
        except Exception as e:
            self.logger.error(f"指定记录更新异常: {e}")
            if self.progress_tracker:
                self.progress_tracker.complete_session(UpdateStatus.FAILED)
            raise
    
    async def _get_records_to_update(self, filter_recent: bool = True) -> List[CampaignTweetSnapshot]:
        """获取需要更新的记录"""
        
        # 构建查询 - 查找缺失字段的记录
        query_builder = CampaignTweetSnapshotQuery()
        
        # 添加条件：缺失关键字段
        query_builder.where("""
            (author_name IS NULL OR author_name = '' OR
             tweet_time_utc IS NULL OR
             views IS NULL)
        """)
        
        # 如果启用过滤最近更新
        if filter_recent:
            threshold_time = datetime.now() - timedelta(hours=self.config.recent_update_threshold_hours)
            query_builder.where("created_at < %s", threshold_time)
        
        # 按ID排序，确保一致的处理顺序
        query_builder.order_by("id", "ASC")
        
        # 执行查询
        records = await self.db_service.execute_custom_query(query_builder)
        
        self.logger.info("查询条件: 缺失关键字段的记录")
        if filter_recent:
            self.logger.info(f"排除最近 {self.config.recent_update_threshold_hours} 小时内的记录")
        
        return records
    
    async def _process_batch(self, batch_info: BatchInfo) -> AsyncGenerator[BatchResult, None]:
        """处理单个批次 - 异步生成器"""
        
        self.progress_tracker.start_batch(batch_info)
        batch_start_time = time.time()
        
        successful_records = []
        failed_records = []
        skipped_records = []
        errors = []
        
        self.logger.info(f"开始处理批次 {batch_info.batch_id}: {batch_info.size} 条记录")
        
        for record in batch_info.records:
            try:
                # 检查是否需要更新
                needs_update, missing_fields = self._check_record_needs_update(record)
                
                if not needs_update:
                    skipped_records.append(record)
                    self.progress_tracker.update_record_status(
                        record.id, UpdateStatus.SKIPPED, "记录已完整，无需更新")
                    continue
                
                # 速率限制控制
                await self.rate_limiter.wait_if_needed()
                
                # 更新记录
                update_start = time.time()
                success, updated_record, error = await self._update_single_record(record, missing_fields)
                update_time = time.time() - update_start
                
                if success:
                    successful_records.append(updated_record)
                    self.progress_tracker.update_record_status(
                        record.id, 
                        UpdateStatus.COMPLETED,
                        updated_fields=missing_fields,
                        processing_time=update_time
                    )
                    self.rate_limiter.record_request(True, update_time)
                    
                    self.logger.debug(f"记录 {record.id} 更新成功: {missing_fields}")
                    
                else:
                    failed_records.append(record)
                    errors.append({
                        'record_id': record.id,
                        'tweet_id': record.tweet_id,
                        'error': error
                    })
                    self.progress_tracker.update_record_status(
                        record.id, 
                        UpdateStatus.FAILED,
                        error_message=error,
                        processing_time=update_time
                    )
                    self.rate_limiter.record_request(False, update_time, error)
                    
                    self.logger.warning(f"记录 {record.id} 更新失败: {error}")
                
            except Exception as e:
                failed_records.append(record)
                error_msg = f"处理异常: {str(e)}"
                errors.append({
                    'record_id': record.id,
                    'tweet_id': record.tweet_id,
                    'error': error_msg
                })
                
                self.progress_tracker.update_record_status(
                    record.id, 
                    UpdateStatus.FAILED,
                    error_message=error_msg
                )
                self.rate_limiter.record_request(False, 0.0, "exception")
                
                self.logger.error(f"记录 {record.id} 处理异常: {e}")
        
        # 创建批次结果
        batch_result = BatchResult(
            batch_info=batch_info,
            success_count=len(successful_records),
            failure_count=len(failed_records),
            errors=errors,
            processing_time=time.time() - batch_start_time,
            updated_records=successful_records,
            skipped_records=skipped_records
        )
        
        success_rate = (len(successful_records) / batch_info.size * 100) if batch_info.size > 0 else 0
        self.logger.info(f"批次 {batch_info.batch_id} 处理完成: "
                        f"{len(successful_records)}/{batch_info.size} 成功 ({success_rate:.1f}%)")
        
        yield batch_result
    
    def _check_record_needs_update(self, record: CampaignTweetSnapshot) -> tuple[bool, List[str]]:
        """检查记录是否需要更新"""
        missing_fields = []
        
        # 检查各个字段
        if not record.author_name or record.author_name.strip() == "":
            missing_fields.append("author_name")
        
        if not record.tweet_time_utc:
            missing_fields.append("tweet_time_utc")
        
        # 检查views字段：如果为None或0，需要更新
        if record.views is None or record.views == 0:
            missing_fields.append("views")
        
        return len(missing_fields) > 0, missing_fields
    
    async def _update_single_record(self, 
                                  record: CampaignTweetSnapshot, 
                                  missing_fields: List[str]) -> tuple[bool, CampaignTweetSnapshot, str]:
        """更新单条记录"""
        try:
            # 构建推文URL
            tweet_url = f"https://twitter.com/{record.author_username}/status/{record.tweet_id}"
            
            # 调用comprehensive API获取完整数据
            comprehensive_data = await self.twitter_service.get_comprehensive_data(tweet_url)
            
            if not comprehensive_data or not comprehensive_data.get('primary_tweet'):
                return False, record, "无法获取推文综合数据"
            
            primary_tweet = comprehensive_data['primary_tweet']
            updated_fields = []
            
            # 添加调试日志
            self.logger.info(f"调试信息 - 记录 {record.id}:")
            self.logger.info(f"   缺失字段: {missing_fields}")
            self.logger.info(f"   primary_tweet keys: {list(primary_tweet.keys())}")
            
            # 更新缺失的字段
            if 'author_name' in missing_fields:
                author = primary_tweet.get('author', {})
                self.logger.info(f"   author 数据: {author}")
                
                # 尝试多种可能的author_name字段
                author_name = None
                if isinstance(author, dict):
                    author_name = (
                        author.get('name') or 
                        author.get('display_name') or 
                        author.get('displayName') or
                        author.get('screen_name') or
                        author.get('username')
                    )
                
                self.logger.info(f"   提取到的 author_name: {repr(author_name)}")
                
                if author_name:
                    record.author_name = str(author_name).strip()
                    updated_fields.append('author_name')
                    self.logger.info(f"   将更新 author_name: {record.author_name}")
                else:
                    self.logger.warning(f"   未能提取到有效的 author_name")
            
            if 'tweet_time_utc' in missing_fields:
                timestamp = primary_tweet.get('timestamp') or primary_tweet.get('time')
                if timestamp:
                    # 转换时间戳格式
                    if isinstance(timestamp, str):
                        try:
                            # 尝试解析不同的时间格式
                            if 'T' in timestamp:
                                record.tweet_time_utc = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            else:
                                record.tweet_time_utc = datetime.fromisoformat(timestamp)
                            updated_fields.append('tweet_time_utc')
                        except ValueError as e:
                            self.logger.warning(f"时间格式解析失败: {timestamp}, 错误: {e}")
            
            # 更新views字段
            if 'views' in missing_fields:
                # 尝试从不同的数据结构中提取views
                views_value = None
                
                # 1. 从metrics中获取
                metrics = primary_tweet.get('metrics', {})
                if isinstance(metrics, dict):
                    views_value = (
                        metrics.get('views') or 
                        metrics.get('view_count') or
                        metrics.get('impressions')
                    )
                
                # 2. 直接从primary_tweet中获取
                if views_value is None:
                    views_value = (
                        primary_tweet.get('views') or
                        primary_tweet.get('view_count') or
                        primary_tweet.get('impressions') or
                        primary_tweet.get('engagement_stats', {}).get('views')
                    )
                
                self.logger.info(f"   提取到的 views: {repr(views_value)}")
                
                # 确保views是一个有效的数字
                if views_value is not None:
                    try:
                        # 处理字符串数字（如"1.2K", "5M"）
                        if isinstance(views_value, str):
                            views_value = views_value.replace(',', '').strip()
                            
                            # 处理K, M等后缀
                            if views_value.endswith('K') or views_value.endswith('k'):
                                views_value = float(views_value[:-1]) * 1000
                            elif views_value.endswith('M') or views_value.endswith('m'):
                                views_value = float(views_value[:-1]) * 1000000
                            else:
                                views_value = float(views_value)
                        
                        views_value = int(views_value)
                        
                        if views_value > 0:  # 只有大于0的views才更新
                            record.views = views_value
                            updated_fields.append('views')
                            self.logger.info(f"   将更新 views: {record.views}")
                        else:
                            self.logger.warning(f"   获取到的 views 值为 0 或负数: {views_value}")
                    
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"   views 值格式转换失败: {views_value}, 错误: {e}")
                else:
                    self.logger.warning(f"   未能提取到有效的 views 值")
            
            # 保存更新到数据库
            if updated_fields:
                success = await self.db_service.update_record(record)
                if success:
                    return True, record, ""
                else:
                    return False, record, "数据库更新失败"
            else:
                return False, record, "没有可更新的字段"
                
        except Exception as e:
            return False, record, f"更新过程异常: {str(e)}"
    
    def _on_batch_complete(self, batch_num: int, total_batches: int, batch_result: BatchResult):
        """批次完成回调"""
        self.progress_tracker.complete_batch(batch_result)
        
        progress = (batch_num / total_batches) * 100
        self.logger.info(f"进度: {batch_num}/{total_batches} 批次 ({progress:.1f}%)")
    
    def _create_update_result(self, 
                            records_to_update: List[CampaignTweetSnapshot],
                            batch_results: List[BatchResult],
                            processing_time: float,
                            session_id: str) -> UpdateResult:
        """创建更新结果"""
        
        total_records = len(records_to_update)
        successful_updates = sum(r.success_count for r in batch_results)
        failed_updates = sum(r.failure_count for r in batch_results)
        skipped_records = sum(len(r.skipped_records) for r in batch_results)
        
        processed_records = successful_updates + failed_updates
        success_rate = (successful_updates / processed_records * 100) if processed_records > 0 else 0.0
        
        # 收集所有错误
        all_errors = []
        for batch_result in batch_results:
            all_errors.extend([
                f"批次 {batch_result.batch_info.batch_id}: {error.get('error', 'Unknown')}"
                for error in batch_result.errors
            ])
        
        return UpdateResult(
            total_records=total_records,
            processed_records=processed_records,
            successful_updates=successful_updates,
            failed_updates=failed_updates,
            skipped_records=skipped_records,
            processing_time=processing_time,
            success_rate=success_rate,
            errors=all_errors,
            session_id=session_id
        )
    
    def get_progress_summary(self) -> Optional[Dict[str, Any]]:
        """获取进度摘要"""
        if self.progress_tracker:
            return self.progress_tracker.get_summary()
        return None
    
    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """获取速率限制器统计"""
        return self.rate_limiter.get_statistics()
    
    def get_batch_manager_stats(self) -> Dict[str, Any]:
        """获取批处理管理器统计"""
        return self.batch_manager.get_statistics()


# 便捷函数和工厂方法

async def create_data_updater(config: UpdaterConfig = None) -> TweetDataUpdater:
    """创建数据更新器实例 - 工厂方法"""
    
    # 导入服务
    from ..database import get_database_service
    
    # 获取数据库服务
    db_service = await get_database_service()
    
    # 独立创建Twitter服务（不依赖Flask容器）
    twitter_service = await _create_standalone_twitter_service()
    
    # 创建更新器
    updater = TweetDataUpdater(
        database_service=db_service,
        twitter_service=twitter_service,
        config=config or UpdaterConfig.create_safe_config()
    )
    
    return updater


async def _create_standalone_twitter_service():
    """独立创建Twitter服务（用于数据更新脚本）"""
    import os
    from ..twitter.service import TwitterService
    from ..data_sources.manager import DataSourceManager
    from ..data_sources.playwright_pooled import PlaywrightPooledSource
    from ..data_sources.twitter_api import TwitterAPISource
    from ..data_sources.apify_source import ApifyTwitterSource
    from ..utils.async_runner import AsyncRunner
    
    # 创建数据源
    sources = []
    
    # 1. Playwright数据源
    try:
        playwright_source = PlaywrightPooledSource(
            pool_min_size=int(os.getenv('BROWSER_POOL_MIN_SIZE', '2')),
            pool_max_size=int(os.getenv('BROWSER_POOL_MAX_SIZE', '4')),  # 数据更新时减少并发
            max_concurrent_requests=int(os.getenv('BROWSER_POOL_MAX_CONCURRENT_REQUESTS', '2'))
        )
        sources.append(playwright_source)
    except Exception as e:
        logging.warning(f"无法创建Playwright数据源: {e}")
    
    # 2. Twitter API数据源
    bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
    if bearer_token:
        try:
            twitter_api_source = TwitterAPISource(bearer_token=bearer_token)
            sources.append(twitter_api_source)
        except Exception as e:
            logging.warning(f"无法创建Twitter API数据源: {e}")
    
    # 3. Apify数据源（如果配置了）
    apify_token = os.getenv('APIFY_API_TOKEN')
    apify_enabled = os.getenv('APIFY_ENABLE', 'false').lower() == 'true'
    if apify_enabled and apify_token:
        try:
            apify_source = ApifyTwitterSource(
                api_token=apify_token,
                actor_id=os.getenv('APIFY_ACTOR_ID', 'apidojo/tweet-scraper'),
                timeout=int(os.getenv('APIFY_TIMEOUT', '120'))
            )
            sources.append(apify_source)
        except Exception as e:
            logging.warning(f"无法创建Apify数据源: {e}")
    
    if not sources:
        raise RuntimeError("没有可用的数据源，请检查配置")
    
    # 创建数据源管理器
    data_manager = DataSourceManager(sources=sources)
    
    # 创建异步运行器
    async_runner = AsyncRunner("data_updater")
    
    # 创建Twitter服务
    twitter_service = TwitterService(
        data_manager=data_manager,
        async_runner=async_runner
    )
    
    return twitter_service


async def quick_update_missing_fields(filter_recent: bool = True) -> UpdateResult:
    """快速更新缺失字段 - 便捷方法"""
    
    config = UpdaterConfig.create_safe_config()
    updater = await create_data_updater(config)
    
    result = await updater.update_all_records(
        filter_recent=filter_recent,
        batch_strategy="priority"  # 优先处理缺失字段多的记录
    )
    
    return result
