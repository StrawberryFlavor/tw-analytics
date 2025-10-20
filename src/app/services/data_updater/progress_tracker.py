"""
进度追踪和状态管理器

遵循单一职责原则，专门负责数据更新过程的进度追踪、状态管理和持久化
为732条记录的更新提供详细的监控和恢复能力
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from ..database.models import CampaignTweetSnapshot
from .batch_manager import BatchInfo, BatchResult


class UpdateStatus(Enum):
    """更新状态枚举"""
    PENDING = "pending"           # 待处理
    IN_PROGRESS = "in_progress"   # 处理中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"            # 失败
    SKIPPED = "skipped"          # 跳过
    PAUSED = "paused"            # 暂停
    CANCELLED = "cancelled"       # 取消


@dataclass
class RecordProgress:
    """单条记录的进度信息"""
    record_id: int
    tweet_id: str
    status: UpdateStatus
    attempt_count: int = 0
    last_attempt_time: Optional[datetime] = None
    error_message: Optional[str] = None
    updated_fields: List[str] = None
    processing_time: float = 0.0
    
    def __post_init__(self):
        if self.updated_fields is None:
            self.updated_fields = []


@dataclass
class BatchProgress:
    """批次进度信息"""
    batch_id: int
    batch_size: int
    status: UpdateStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    skip_count: int = 0
    error_messages: List[str] = None
    processing_time: float = 0.0
    records: List[RecordProgress] = None
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []
        if self.records is None:
            self.records = []


@dataclass
class OverallProgress:
    """整体进度信息"""
    session_id: str
    total_records: int
    processed_records: int = 0
    successful_records: int = 0
    failed_records: int = 0
    skipped_records: int = 0
    
    total_batches: int = 0
    processed_batches: int = 0
    successful_batches: int = 0
    failed_batches: int = 0
    
    start_time: Optional[datetime] = None
    last_update_time: Optional[datetime] = None
    estimated_completion_time: Optional[datetime] = None
    
    status: UpdateStatus = UpdateStatus.PENDING
    current_phase: str = "初始化"
    error_summary: List[str] = None
    
    def __post_init__(self):
        if self.error_summary is None:
            self.error_summary = []
    
    @property
    def progress_percentage(self) -> float:
        """计算完成百分比"""
        if self.total_records == 0:
            return 0.0
        return (self.processed_records / self.total_records) * 100
    
    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.processed_records == 0:
            return 0.0
        return (self.successful_records / self.processed_records) * 100
    
    @property
    def elapsed_time(self) -> float:
        """计算已用时间（秒）"""
        if not self.start_time:
            return 0.0
        end_time = self.last_update_time or datetime.now()
        return (end_time - self.start_time).total_seconds()
    
    @property
    def estimated_remaining_time(self) -> float:
        """估算剩余时间（秒）"""
        if self.processed_records == 0 or self.progress_percentage >= 100:
            return 0.0
        
        elapsed = self.elapsed_time
        if elapsed == 0:
            return 0.0
        
        records_per_second = self.processed_records / elapsed
        remaining_records = self.total_records - self.processed_records
        
        return remaining_records / records_per_second if records_per_second > 0 else 0.0


class ProgressTracker:
    """进度追踪器 - 单一职责原则"""
    
    def __init__(self, 
                 session_id: str = None,
                 progress_file_path: str = None,
                 auto_save_interval: int = 10):
        """
        初始化进度追踪器
        
        Args:
            session_id: 会话ID
            progress_file_path: 进度文件路径
            auto_save_interval: 自动保存间隔（秒）
        """
        self.session_id = session_id or f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.progress_file_path = progress_file_path or f"progress_{self.session_id}.json"
        self.auto_save_interval = auto_save_interval
        
        # 确保进度文件目录存在
        progress_dir = Path(self.progress_file_path).parent
        progress_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        
        # 进度数据
        self.overall_progress = OverallProgress(session_id=self.session_id, total_records=0)
        self.batch_progress: Dict[int, BatchProgress] = {}
        self.record_progress: Dict[int, RecordProgress] = {}
        
        # 回调函数
        self._progress_callbacks: List[Callable[[OverallProgress], None]] = []
        self._batch_callbacks: List[Callable[[BatchProgress], None]] = []
        self._record_callbacks: List[Callable[[RecordProgress], None]] = []
        
        # 自动保存任务
        self._auto_save_task: Optional[asyncio.Task] = None
        self._should_stop_auto_save = False
        
        self.logger.info(f"📊 进度追踪器初始化完成: {self.session_id}")
    
    def initialize_session(self, total_records: int, total_batches: int = 0):
        """初始化会话"""
        self.overall_progress.total_records = total_records
        self.overall_progress.total_batches = total_batches
        self.overall_progress.start_time = datetime.now()
        self.overall_progress.last_update_time = datetime.now()
        self.overall_progress.status = UpdateStatus.IN_PROGRESS
        self.overall_progress.current_phase = "准备数据"
        
        self.logger.info(f"🚀 会话初始化: {total_records} 条记录, {total_batches} 个批次")
        
        # 启动自动保存
        self.start_auto_save()
    
    def update_phase(self, phase_name: str):
        """更新当前阶段"""
        self.overall_progress.current_phase = phase_name
        self.overall_progress.last_update_time = datetime.now()
        self.logger.info(f"📋 阶段更新: {phase_name}")
        self._notify_progress_callbacks()
    
    def start_batch(self, batch_info: BatchInfo):
        """开始批次处理"""
        batch_progress = BatchProgress(
            batch_id=batch_info.batch_id,
            batch_size=batch_info.size,
            status=UpdateStatus.IN_PROGRESS,
            start_time=datetime.now()
        )
        
        # 初始化批次中的记录进度
        for record in batch_info.records:
            record_progress = RecordProgress(
                record_id=record.id or 0,
                tweet_id=record.tweet_id,
                status=UpdateStatus.PENDING
            )
            batch_progress.records.append(record_progress)
            self.record_progress[record.id or 0] = record_progress
        
        self.batch_progress[batch_info.batch_id] = batch_progress
        
        self.overall_progress.current_phase = f"处理批次 {batch_info.batch_id}"
        self.overall_progress.last_update_time = datetime.now()
        
        self.logger.info(f"📦 开始批次 {batch_info.batch_id}: {batch_info.size} 条记录")
        self._notify_batch_callbacks(batch_progress)
    
    def complete_batch(self, batch_result: BatchResult):
        """完成批次处理"""
        batch_id = batch_result.batch_info.batch_id
        
        if batch_id not in self.batch_progress:
            self.logger.warning(f"批次 {batch_id} 未在进度追踪中找到")
            return
        
        batch_progress = self.batch_progress[batch_id]
        batch_progress.end_time = datetime.now()
        batch_progress.processing_time = batch_result.processing_time
        batch_progress.success_count = batch_result.success_count
        batch_progress.failure_count = batch_result.failure_count
        batch_progress.skip_count = len(batch_result.skipped_records)
        
        # 更新批次状态
        if batch_result.failure_count == 0:
            batch_progress.status = UpdateStatus.COMPLETED
        elif batch_result.success_count == 0:
            batch_progress.status = UpdateStatus.FAILED
        else:
            batch_progress.status = UpdateStatus.COMPLETED  # 部分成功也算完成
        
        # 记录错误信息
        batch_progress.error_messages = [error.get('error', 'Unknown error') 
                                       for error in batch_result.errors]
        
        # 更新整体进度
        self.overall_progress.processed_batches += 1
        self.overall_progress.processed_records += batch_result.success_count + batch_result.failure_count
        self.overall_progress.successful_records += batch_result.success_count
        self.overall_progress.failed_records += batch_result.failure_count
        self.overall_progress.skipped_records += len(batch_result.skipped_records)
        
        if batch_progress.status == UpdateStatus.COMPLETED:
            self.overall_progress.successful_batches += 1
        else:
            self.overall_progress.failed_batches += 1
        
        # 更新时间信息
        self.overall_progress.last_update_time = datetime.now()
        
        # 估算完成时间
        self._update_estimated_completion_time()
        
        self.logger.info(f"✅ 批次 {batch_id} 完成: {batch_result.success_count}/{batch_result.batch_info.size} 成功")
        
        self._notify_batch_callbacks(batch_progress)
        self._notify_progress_callbacks()
    
    def update_record_status(self, 
                           record_id: int, 
                           status: UpdateStatus,
                           error_message: str = None,
                           updated_fields: List[str] = None,
                           processing_time: float = 0.0):
        """更新记录状态"""
        if record_id not in self.record_progress:
            # 创建新的记录进度
            self.record_progress[record_id] = RecordProgress(
                record_id=record_id,
                tweet_id=f"record_{record_id}",
                status=status
            )
        
        record_progress = self.record_progress[record_id]
        record_progress.status = status
        record_progress.last_attempt_time = datetime.now()
        record_progress.attempt_count += 1
        record_progress.processing_time = processing_time
        
        if error_message:
            record_progress.error_message = error_message
        
        if updated_fields:
            record_progress.updated_fields.extend(updated_fields)
        
        self._notify_record_callbacks(record_progress)
    
    def _update_estimated_completion_time(self):
        """更新预估完成时间"""
        remaining_time = self.overall_progress.estimated_remaining_time
        if remaining_time > 0:
            self.overall_progress.estimated_completion_time = datetime.now() + timedelta(seconds=remaining_time)
        else:
            self.overall_progress.estimated_completion_time = datetime.now()
    
    def complete_session(self, status: UpdateStatus = UpdateStatus.COMPLETED):
        """完成会话"""
        self.overall_progress.status = status
        self.overall_progress.last_update_time = datetime.now()
        self.overall_progress.current_phase = "完成" if status == UpdateStatus.COMPLETED else status.value
        
        # 停止自动保存
        self.stop_auto_save()
        
        # 最后保存一次
        self.save_progress()
        
        self.logger.info(f"🏁 会话完成: {status.value}")
        self.logger.info(f"📊 最终统计: {self.overall_progress.successful_records}/{self.overall_progress.total_records} 成功")
        
        self._notify_progress_callbacks()
    
    def add_progress_callback(self, callback: Callable[[OverallProgress], None]):
        """添加整体进度回调"""
        self._progress_callbacks.append(callback)
    
    def add_batch_callback(self, callback: Callable[[BatchProgress], None]):
        """添加批次进度回调"""
        self._batch_callbacks.append(callback)
    
    def add_record_callback(self, callback: Callable[[RecordProgress], None]):
        """添加记录进度回调"""
        self._record_callbacks.append(callback)
    
    def _notify_progress_callbacks(self):
        """通知整体进度回调"""
        for callback in self._progress_callbacks:
            try:
                callback(self.overall_progress)
            except Exception as e:
                self.logger.error(f"进度回调异常: {e}")
    
    def _notify_batch_callbacks(self, batch_progress: BatchProgress):
        """通知批次进度回调"""
        for callback in self._batch_callbacks:
            try:
                callback(batch_progress)
            except Exception as e:
                self.logger.error(f"批次回调异常: {e}")
    
    def _notify_record_callbacks(self, record_progress: RecordProgress):
        """通知记录进度回调"""
        for callback in self._record_callbacks:
            try:
                callback(record_progress)
            except Exception as e:
                self.logger.error(f"记录回调异常: {e}")
    
    def save_progress(self) -> bool:
        """保存进度到文件"""
        try:
            progress_data = {
                'session_id': self.session_id,
                'overall_progress': self._serialize_overall_progress(),
                'batch_progress': {str(k): self._serialize_batch_progress(v) 
                                 for k, v in self.batch_progress.items()},
                'record_progress': {str(k): self._serialize_record_progress(v) 
                                  for k, v in self.record_progress.items()},
                'saved_at': datetime.now().isoformat()
            }
            
            # 原子写入
            temp_file = self.progress_file_path + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2, ensure_ascii=False, default=str)
            
            # 原子替换
            os.replace(temp_file, self.progress_file_path)
            
            self.logger.debug(f"💾 进度已保存: {self.progress_file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 保存进度失败: {e}")
            return False
    
    def load_progress(self) -> bool:
        """从文件加载进度"""
        try:
            if not os.path.exists(self.progress_file_path):
                self.logger.info("进度文件不存在，使用新会话")
                return False
            
            with open(self.progress_file_path, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            
            # 恢复整体进度
            overall_data = progress_data.get('overall_progress', {})
            self.overall_progress = self._deserialize_overall_progress(overall_data)
            
            # 恢复批次进度
            batch_data = progress_data.get('batch_progress', {})
            self.batch_progress = {int(k): self._deserialize_batch_progress(v) 
                                 for k, v in batch_data.items()}
            
            # 恢复记录进度
            record_data = progress_data.get('record_progress', {})
            self.record_progress = {int(k): self._deserialize_record_progress(v) 
                                  for k, v in record_data.items()}
            
            self.logger.info(f"📂 进度已恢复: {self.session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 加载进度失败: {e}")
            return False
    
    def _serialize_overall_progress(self) -> dict:
        """序列化整体进度"""
        data = asdict(self.overall_progress)
        data['status'] = self.overall_progress.status.value
        return data
    
    def _deserialize_overall_progress(self, data: dict) -> OverallProgress:
        """反序列化整体进度"""
        if 'status' in data:
            data['status'] = UpdateStatus(data['status'])
        
        # 转换时间字段
        for field in ['start_time', 'last_update_time', 'estimated_completion_time']:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except:
                    data[field] = None
        
        return OverallProgress(**data)
    
    def _serialize_batch_progress(self, batch_progress: BatchProgress) -> dict:
        """序列化批次进度"""
        data = asdict(batch_progress)
        data['status'] = batch_progress.status.value
        data['records'] = [self._serialize_record_progress(r) for r in batch_progress.records]
        return data
    
    def _deserialize_batch_progress(self, data: dict) -> BatchProgress:
        """反序列化批次进度"""
        if 'status' in data:
            data['status'] = UpdateStatus(data['status'])
        
        # 转换时间字段
        for field in ['start_time', 'end_time']:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except:
                    data[field] = None
        
        # 转换记录数组
        if 'records' in data:
            data['records'] = [self._deserialize_record_progress(r) for r in data['records']]
        
        return BatchProgress(**data)
    
    def _serialize_record_progress(self, record_progress: RecordProgress) -> dict:
        """序列化记录进度"""
        data = asdict(record_progress)
        data['status'] = record_progress.status.value
        return data
    
    def _deserialize_record_progress(self, data: dict) -> RecordProgress:
        """反序列化记录进度"""
        if 'status' in data:
            data['status'] = UpdateStatus(data['status'])
        
        if data.get('last_attempt_time'):
            try:
                data['last_attempt_time'] = datetime.fromisoformat(data['last_attempt_time'])
            except:
                data['last_attempt_time'] = None
        
        return RecordProgress(**data)
    
    def start_auto_save(self):
        """启动自动保存"""
        if self._auto_save_task is not None:
            return
        
        self._should_stop_auto_save = False
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())
        self.logger.debug(f"🔄 自动保存已启动，间隔: {self.auto_save_interval}s")
    
    def stop_auto_save(self):
        """停止自动保存"""
        self._should_stop_auto_save = True
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None
        self.logger.debug("⏹️  自动保存已停止")
    
    async def _auto_save_loop(self):
        """自动保存循环"""
        try:
            while not self._should_stop_auto_save:
                await asyncio.sleep(self.auto_save_interval)
                if not self._should_stop_auto_save:
                    self.save_progress()
        except asyncio.CancelledError:
            self.logger.debug("自动保存任务已取消")
        except Exception as e:
            self.logger.error(f"自动保存异常: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取进度摘要"""
        return {
            'session_id': self.session_id,
            'progress_percentage': self.overall_progress.progress_percentage,
            'success_rate': self.overall_progress.success_rate,
            'elapsed_time': self.overall_progress.elapsed_time,
            'estimated_remaining_time': self.overall_progress.estimated_remaining_time,
            'current_phase': self.overall_progress.current_phase,
            'status': self.overall_progress.status.value,
            'records': {
                'total': self.overall_progress.total_records,
                'processed': self.overall_progress.processed_records,
                'successful': self.overall_progress.successful_records,
                'failed': self.overall_progress.failed_records,
                'remaining': self.overall_progress.total_records - self.overall_progress.processed_records
            },
            'batches': {
                'total': self.overall_progress.total_batches,
                'processed': self.overall_progress.processed_batches,
                'successful': self.overall_progress.successful_batches,
                'failed': self.overall_progress.failed_batches
            }
        }
    
    def get_failed_records(self) -> List[RecordProgress]:
        """获取失败的记录列表"""
        return [record for record in self.record_progress.values() 
                if record.status == UpdateStatus.FAILED]
    
    def get_pending_records(self) -> List[RecordProgress]:
        """获取待处理的记录列表"""
        return [record for record in self.record_progress.values() 
                if record.status == UpdateStatus.PENDING]