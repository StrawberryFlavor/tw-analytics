"""
数据同步模型
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum


class SyncOperation(Enum):
    """同步操作类型"""
    CREATE = "create"      # 创建新记录
    UPDATE = "update"      # 更新现有记录
    SKIP = "skip"         # 跳过（已存在且一致）


@dataclass
class TaskSubmission:
    """campaign_task_submission 数据模型"""
    id: int
    task_id: int
    submitter_uid: int
    x_tweet_id: Optional[str]
    x_type: str  # 'comment', 'retweet', 'post'
    x_linked_to: Optional[str]
    is_valid: Optional[int]
    view_count: Optional[int]
    reward_amount: Optional[float]
    status: Optional[str]  # 'pending', 'approved', 'invalid', 'valid'
    created_at: Optional[datetime]
    is_del: int
    updated_at: Optional[datetime]
    yaps: Optional[int]


@dataclass
class SyncRecord:
    """同步记录"""
    tweet_id: str
    operation: SyncOperation
    submission_data: TaskSubmission
    reason: str = ""
    
    def __str__(self):
        return f"SyncRecord(tweet_id={self.tweet_id}, op={self.operation.value}, reason={self.reason})"