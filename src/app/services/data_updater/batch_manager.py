"""
批处理管理器

遵循SOLID原则，专门管理大规模数据的批量处理
针对732条记录的高效更新策略
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
import math

from ..database.models import CampaignTweetSnapshot
from ...core.config_factory import UpdaterConfig
from .rate_limiter import BatchRateLimiter


@dataclass
class BatchInfo:
    """批次信息 - 数据结构"""
    batch_id: int
    start_index: int
    end_index: int
    size: int
    records: List[CampaignTweetSnapshot]
    priority: int = 0  # 优先级（数字越小优先级越高）
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class BatchResult:
    """批次处理结果"""
    batch_info: BatchInfo
    success_count: int
    failure_count: int
    errors: List[Dict[str, Any]]
    processing_time: float
    updated_records: List[CampaignTweetSnapshot]
    skipped_records: List[CampaignTweetSnapshot]


class BatchStrategy:
    """批处理策略 - 策略模式"""
    
    @staticmethod
    def create_equal_batches(records: List[CampaignTweetSnapshot], 
                           batch_size: int) -> List[BatchInfo]:
        """创建等大小批次"""
        batches = []
        total_records = len(records)
        
        for i in range(0, total_records, batch_size):
            end_index = min(i + batch_size, total_records)
            batch_records = records[i:end_index]
            
            batch_info = BatchInfo(
                batch_id=len(batches) + 1,
                start_index=i,
                end_index=end_index - 1,
                size=len(batch_records),
                records=batch_records
            )
            batches.append(batch_info)
        
        return batches
    
    @staticmethod
    def create_priority_batches(records: List[CampaignTweetSnapshot], 
                              batch_size: int,
                              priority_fn: Callable[[CampaignTweetSnapshot], int]) -> List[BatchInfo]:
        """创建优先级批次"""
        # 按优先级排序
        sorted_records = sorted(records, key=priority_fn)
        
        # 创建批次
        batches = []
        for i in range(0, len(sorted_records), batch_size):
            end_index = min(i + batch_size, len(sorted_records))
            batch_records = sorted_records[i:end_index]
            
            # 计算批次优先级（最高优先级记录的优先级）
            batch_priority = min(priority_fn(record) for record in batch_records)
            
            batch_info = BatchInfo(
                batch_id=len(batches) + 1,
                start_index=i,
                end_index=end_index - 1,
                size=len(batch_records),
                records=batch_records,
                priority=batch_priority
            )
            batches.append(batch_info)
        
        # 按优先级排序批次
        batches.sort(key=lambda b: b.priority)
        
        # 重新分配批次ID
        for idx, batch in enumerate(batches):
            batch.batch_id = idx + 1
        
        return batches
    
    @staticmethod
    def create_adaptive_batches(records: List[CampaignTweetSnapshot], 
                              base_batch_size: int,
                              complexity_fn: Callable[[CampaignTweetSnapshot], float]) -> List[BatchInfo]:
        """创建自适应大小批次 - 根据复杂度调整批次大小"""
        batches = []
        current_batch = []
        current_complexity = 0.0
        max_complexity_per_batch = base_batch_size * 1.0  # 基准复杂度
        
        for record in records:
            record_complexity = complexity_fn(record)
            
            # 检查是否需要开始新批次
            if (len(current_batch) >= base_batch_size or 
                (current_batch and current_complexity + record_complexity > max_complexity_per_batch)):
                
                # 创建当前批次
                batch_info = BatchInfo(
                    batch_id=len(batches) + 1,
                    start_index=len(batches) * base_batch_size,  # 估算
                    end_index=len(batches) * base_batch_size + len(current_batch) - 1,
                    size=len(current_batch),
                    records=current_batch.copy()
                )
                batches.append(batch_info)
                
                # 重置当前批次
                current_batch = []
                current_complexity = 0.0
            
            current_batch.append(record)
            current_complexity += record_complexity
        
        # 处理最后一个批次
        if current_batch:
            batch_info = BatchInfo(
                batch_id=len(batches) + 1,
                start_index=len(batches) * base_batch_size,
                end_index=len(batches) * base_batch_size + len(current_batch) - 1,
                size=len(current_batch),
                records=current_batch
            )
            batches.append(batch_info)
        
        return batches


class BatchManager:
    """批处理管理器 - 单一职责原则"""
    
    def __init__(self, 
                 config: UpdaterConfig,
                 rate_limiter: BatchRateLimiter = None):
        """
        初始化批处理管理器
        
        Args:
            config: 更新器配置
            rate_limiter: 速率限制器
        """
        self.config = config
        self.rate_limiter = rate_limiter or BatchRateLimiter(
            requests_per_minute=config.requests_per_minute,
            requests_per_hour=config.requests_per_hour,
            base_delay=config.request_delay_seconds,
            batch_delay=config.batch_delay_seconds
        )
        
        self.logger = logging.getLogger(__name__)
        
        # 批处理统计
        self._total_batches = 0
        self._processed_batches = 0
        self._failed_batches = 0
        self._total_records = 0
        self._processed_records = 0
        self._failed_records = 0
        
        # 状态管理
        self._is_running = False
        self._is_paused = False
        self._should_stop = False
        
    def create_batches(self, 
                      records: List[CampaignTweetSnapshot],
                      strategy: str = "equal") -> List[BatchInfo]:
        """创建批次 - 工厂方法"""
        
        if not records:
            return []
        
        self.logger.info(f"📦 创建批次: {len(records)} 条记录, 策略: {strategy}")
        
        if strategy == "equal":
            batches = BatchStrategy.create_equal_batches(records, self.config.batch_size)
            
        elif strategy == "priority":
            def priority_function(record: CampaignTweetSnapshot) -> int:
                """优先级函数 - 缺失字段越多优先级越高"""
                priority = 0
                if not record.author_name:
                    priority += 10  # 缺失作者名最重要
                if not record.tweet_time_utc:
                    priority += 5   # 缺失时间较重要
                return priority
                
            batches = BatchStrategy.create_priority_batches(
                records, self.config.batch_size, priority_function)
            
        elif strategy == "adaptive":
            def complexity_function(record: CampaignTweetSnapshot) -> float:
                """复杂度函数 - 预估处理复杂度"""
                complexity = 1.0  # 基础复杂度
                
                # 缺失字段越多越复杂
                missing_fields = 0
                if not record.author_name:
                    missing_fields += 1
                if not record.tweet_time_utc:
                    missing_fields += 1
                
                complexity += missing_fields * 0.5
                
                # 推文类型影响复杂度
                if record.tweet_type in ['quote', 'reply']:
                    complexity += 0.3
                    
                return complexity
                
            batches = BatchStrategy.create_adaptive_batches(
                records, self.config.batch_size, complexity_function)
        else:
            raise ValueError(f"未知的批处理策略: {strategy}")
        
        self._total_batches = len(batches)
        self._total_records = len(records)
        
        self.logger.info(f"✅ 批次创建完成: {len(batches)} 个批次")
        
        # 打印批次分布统计
        batch_sizes = [batch.size for batch in batches]
        avg_size = sum(batch_sizes) / len(batch_sizes) if batch_sizes else 0
        min_size = min(batch_sizes) if batch_sizes else 0
        max_size = max(batch_sizes) if batch_sizes else 0
        
        self.logger.info(f"📊 批次统计: 平均大小 {avg_size:.1f}, 范围 {min_size}-{max_size}")
        
        return batches
    
    async def process_batches(self, 
                            batches: List[BatchInfo],
                            batch_processor: Callable[[BatchInfo], AsyncGenerator[BatchResult, None]],
                            progress_callback: Optional[Callable[[int, int, BatchResult], None]] = None) -> List[BatchResult]:
        """
        处理批次队列
        
        Args:
            batches: 批次列表
            batch_processor: 批次处理器（异步生成器）
            progress_callback: 进度回调函数
            
        Returns:
            批次处理结果列表
        """
        if not batches:
            return []
        
        self.logger.info(f"🚀 开始处理 {len(batches)} 个批次...")
        
        self._is_running = True
        self._should_stop = False
        self._processed_batches = 0
        self._failed_batches = 0
        self._processed_records = 0
        self._failed_records = 0
        
        results = []
        
        try:
            # 如果支持并发处理
            if self.config.max_concurrent_batches > 1:
                results = await self._process_batches_concurrent(
                    batches, batch_processor, progress_callback)
            else:
                results = await self._process_batches_sequential(
                    batches, batch_processor, progress_callback)
                    
        except Exception as e:
            self.logger.error(f"❌ 批次处理异常: {e}")
            raise
        finally:
            self._is_running = False
        
        # 输出总结
        total_success = sum(r.success_count for r in results)
        total_failure = sum(r.failure_count for r in results)
        total_time = sum(r.processing_time for r in results)
        
        self.logger.info(f"✅ 批次处理完成!")
        self.logger.info(f"📊 处理统计:")
        self.logger.info(f"   批次: {self._processed_batches}/{self._total_batches}")
        self.logger.info(f"   记录: 成功 {total_success}, 失败 {total_failure}")
        self.logger.info(f"   时间: {total_time:.1f}s")
        
        return results
    
    async def _process_batches_sequential(self, 
                                        batches: List[BatchInfo],
                                        batch_processor: Callable,
                                        progress_callback: Optional[Callable] = None) -> List[BatchResult]:
        """顺序处理批次"""
        results = []
        
        for i, batch in enumerate(batches):
            if self._should_stop:
                self.logger.info("📢 接收到停止信号，终止处理")
                break
            
            # 检查暂停状态
            while self._is_paused and not self._should_stop:
                self.logger.info("⏸️  处理已暂停，等待恢复...")
                await asyncio.sleep(1)
            
            if self._should_stop:
                break
            
            self.logger.info(f"📦 处理批次 {i+1}/{len(batches)} (ID: {batch.batch_id}, 大小: {batch.size})")
            
            try:
                # 批次间延迟控制
                if i > 0:  # 第一个批次不需要等待
                    await self.rate_limiter.wait_for_batch()
                
                # 处理批次
                start_time = asyncio.get_event_loop().time()
                
                # 使用异步生成器处理批次
                batch_result = None
                async for result in batch_processor(batch):
                    batch_result = result
                    break  # 只取第一个结果
                
                if batch_result is None:
                    # 创建失败结果
                    batch_result = BatchResult(
                        batch_info=batch,
                        success_count=0,
                        failure_count=batch.size,
                        errors=[{"error": "批次处理器没有返回结果"}],
                        processing_time=0.0,
                        updated_records=[],
                        skipped_records=batch.records
                    )
                
                end_time = asyncio.get_event_loop().time()
                batch_result.processing_time = end_time - start_time
                
                results.append(batch_result)
                
                # 更新统计
                self._processed_batches += 1
                self._processed_records += batch_result.success_count
                self._failed_records += batch_result.failure_count
                
                if batch_result.failure_count > 0:
                    self._failed_batches += 1
                
                # 进度回调
                if progress_callback:
                    progress_callback(i + 1, len(batches), batch_result)
                
                # 记录处理结果
                success_rate = batch_result.success_count / batch.size * 100 if batch.size > 0 else 0
                self.logger.info(f"✅ 批次 {batch.batch_id} 完成: {batch_result.success_count}/{batch.size} 成功 ({success_rate:.1f}%)")
                
                if batch_result.errors:
                    self.logger.warning(f"⚠️  批次 {batch.batch_id} 有 {len(batch_result.errors)} 个错误")
                
            except Exception as e:
                self.logger.error(f"❌ 批次 {batch.batch_id} 处理失败: {e}")
                
                # 创建错误结果
                error_result = BatchResult(
                    batch_info=batch,
                    success_count=0,
                    failure_count=batch.size,
                    errors=[{"error": str(e), "batch_id": batch.batch_id}],
                    processing_time=0.0,
                    updated_records=[],
                    skipped_records=batch.records
                )
                results.append(error_result)
                
                self._failed_batches += 1
                self._failed_records += batch.size
                
                # 连续失败检查
                consecutive_failures = sum(1 for r in results[-self.config.max_consecutive_failures:] 
                                         if r.success_count == 0)
                
                if consecutive_failures >= self.config.max_consecutive_failures:
                    self.logger.error(f"❌ 连续 {consecutive_failures} 个批次失败，暂停处理")
                    await asyncio.sleep(self.config.pause_on_error_seconds)
        
        return results
    
    async def _process_batches_concurrent(self, 
                                        batches: List[BatchInfo],
                                        batch_processor: Callable,
                                        progress_callback: Optional[Callable] = None) -> List[BatchResult]:
        """并发处理批次"""
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(self.config.max_concurrent_batches)
        results = []
        completed_count = 0
        
        async def process_single_batch(batch: BatchInfo, index: int) -> BatchResult:
            nonlocal completed_count
            
            async with semaphore:
                if self._should_stop:
                    return None
                
                try:
                    self.logger.info(f"📦 并发处理批次 {index+1}/{len(batches)} (ID: {batch.batch_id})")
                    
                    start_time = asyncio.get_event_loop().time()
                    
                    # 处理批次
                    batch_result = None
                    async for result in batch_processor(batch):
                        batch_result = result
                        break
                    
                    if batch_result is None:
                        batch_result = BatchResult(
                            batch_info=batch,
                            success_count=0,
                            failure_count=batch.size,
                            errors=[{"error": "批次处理器没有返回结果"}],
                            processing_time=0.0,
                            updated_records=[],
                            skipped_records=batch.records
                        )
                    
                    end_time = asyncio.get_event_loop().time()
                    batch_result.processing_time = end_time - start_time
                    
                    completed_count += 1
                    
                    # 进度回调
                    if progress_callback:
                        progress_callback(completed_count, len(batches), batch_result)
                    
                    return batch_result
                    
                except Exception as e:
                    self.logger.error(f"❌ 并发批次 {batch.batch_id} 失败: {e}")
                    return BatchResult(
                        batch_info=batch,
                        success_count=0,
                        failure_count=batch.size,
                        errors=[{"error": str(e)}],
                        processing_time=0.0,
                        updated_records=[],
                        skipped_records=batch.records
                    )
        
        # 创建并发任务
        tasks = [process_single_batch(batch, i) for i, batch in enumerate(batches)]
        
        # 等待所有任务完成
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for result in task_results:
            if isinstance(result, Exception):
                self.logger.error(f"❌ 任务异常: {result}")
                continue
            
            if result is not None:
                results.append(result)
                
                # 更新统计
                self._processed_batches += 1
                self._processed_records += result.success_count
                self._failed_records += result.failure_count
                
                if result.failure_count > 0:
                    self._failed_batches += 1
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取批处理统计信息"""
        processed_rate = (self._processed_batches / self._total_batches * 100) if self._total_batches > 0 else 0
        success_rate = (self._processed_records / (self._processed_records + self._failed_records) * 100) if (self._processed_records + self._failed_records) > 0 else 0
        
        return {
            'status': {
                'is_running': self._is_running,
                'is_paused': self._is_paused,
                'should_stop': self._should_stop
            },
            'batches': {
                'total': self._total_batches,
                'processed': self._processed_batches,
                'failed': self._failed_batches,
                'remaining': self._total_batches - self._processed_batches,
                'processed_percentage': processed_rate
            },
            'records': {
                'total': self._total_records,
                'processed_successfully': self._processed_records,
                'failed': self._failed_records,
                'success_rate': success_rate
            },
            'rate_limiter': self.rate_limiter.get_statistics() if self.rate_limiter else None
        }
    
    def pause(self):
        """暂停处理"""
        self._is_paused = True
        self.logger.info("⏸️  批处理已暂停")
    
    def resume(self):
        """恢复处理"""
        self._is_paused = False
        self.logger.info("▶️  批处理已恢复")
    
    def stop(self):
        """停止处理"""
        self._should_stop = True
        self.logger.info("⏹️  批处理停止信号已发送")
    
    def reset_statistics(self):
        """重置统计信息"""
        self._processed_batches = 0
        self._failed_batches = 0
        self._processed_records = 0
        self._failed_records = 0
        self.logger.info("🔄 统计信息已重置")