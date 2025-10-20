"""
浏览器实例轮换管理器
定期轮换浏览器实例以提升反爬虫效果
"""

import asyncio
import time
import random
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

class RotationReason(Enum):
    """轮换原因枚举"""
    SCHEDULED = "scheduled"  # 计划轮换
    USAGE_LIMIT = "usage_limit"  # 使用次数限制
    TIME_LIMIT = "time_limit"  # 时间限制
    ANTI_DETECTION = "anti_detection"  # 反检测需要

@dataclass
class InstanceRotationConfig:
    """实例轮换配置 (从应用配置自动获取)"""
    max_instance_lifetime: int
    max_usage_count: int
    rotation_probability: float
    min_rotation_interval: int
    batch_rotation_size: int = 1  # 批量轮换大小
    
    @classmethod
    def from_app_config(cls):
        """从应用配置创建轮换配置"""
        from ...config import Config
        
        return cls(
            max_instance_lifetime=Config.BROWSER_POOL_INSTANCE_LIFETIME,
            max_usage_count=Config.get_max_usage_count(),
            rotation_probability=Config.get_rotation_probability(),
            min_rotation_interval=int(Config.get_rotation_check_interval()),
        )

class InstanceRotationManager:
    """浏览器实例轮换管理器"""
    
    def __init__(self, config: InstanceRotationConfig = None):
        self.config = config or InstanceRotationConfig()
        self.logger = logging.getLogger(__name__)
        
        # 实例轮换状态跟踪
        self.instance_creation_time: Dict[str, float] = {}
        self.instance_usage_count: Dict[str, int] = {}
        self.last_rotation_time: Dict[str, float] = {}
        
        # 轮换锁，防止并发轮换
        self._rotation_lock = asyncio.Lock()
        
    def register_instance(self, instance_id: str):
        """注册新实例"""
        current_time = time.time()
        self.instance_creation_time[instance_id] = current_time
        self.instance_usage_count[instance_id] = 0
        self.last_rotation_time[instance_id] = current_time
        
        self.logger.info(f"🔄 注册实例轮换跟踪: {instance_id}")
    
    def record_usage(self, instance_id: str):
        """记录实例使用"""
        if instance_id in self.instance_usage_count:
            self.instance_usage_count[instance_id] += 1
    
    def should_rotate_instance(self, instance_id: str) -> tuple:
        """判断是否应该轮换实例"""
        if instance_id not in self.instance_creation_time:
            return False, None
            
        current_time = time.time()
        creation_time = self.instance_creation_time[instance_id]
        usage_count = self.instance_usage_count.get(instance_id, 0)
        last_rotation = self.last_rotation_time.get(instance_id, creation_time)
        
        # 检查时间限制
        if current_time - creation_time > self.config.max_instance_lifetime:
            return True, RotationReason.TIME_LIMIT
            
        # 检查使用次数限制
        if usage_count >= self.config.max_usage_count:
            return True, RotationReason.USAGE_LIMIT
            
        # 检查最小轮换间隔
        if current_time - last_rotation < self.config.min_rotation_interval:
            return False, None
            
        # 随机轮换（反检测）
        if random.random() < self.config.rotation_probability:
            return True, RotationReason.ANTI_DETECTION
            
        return False, None
    
    def should_scheduled_rotation(self) -> bool:
        """是否应该进行计划性轮换"""
        # 可以基于时间、负载等因素决定
        current_time = time.time()
        
        # 每小时进行一次计划性检查
        for instance_id, creation_time in self.instance_creation_time.items():
            if current_time - creation_time > 3600:  # 1小时
                return True
                
        return False
    
    def cleanup_instance_tracking(self, instance_id: str):
        """清理实例跟踪信息"""
        self.instance_creation_time.pop(instance_id, None)
        self.instance_usage_count.pop(instance_id, None)
        self.last_rotation_time.pop(instance_id, None)
        
        self.logger.info(f"🗑️ 清理实例轮换跟踪: {instance_id}")
    
    def get_instance_stats(self, instance_id: str) -> Dict[str, Any]:
        """获取实例统计信息"""
        if instance_id not in self.instance_creation_time:
            return {}
            
        current_time = time.time()
        creation_time = self.instance_creation_time[instance_id]
        usage_count = self.instance_usage_count.get(instance_id, 0)
        
        return {
            'instance_id': instance_id,
            'lifetime': current_time - creation_time,
            'usage_count': usage_count,
            'remaining_lifetime': max(0, self.config.max_instance_lifetime - (current_time - creation_time)),
            'remaining_usage': max(0, self.config.max_usage_count - usage_count)
        }
    
    def get_rotation_recommendation(self) -> Dict[str, Any]:
        """获取轮换建议"""
        recommendations = []
        
        for instance_id in self.instance_creation_time.keys():
            should_rotate, reason = self.should_rotate_instance(instance_id)
            if should_rotate:
                stats = self.get_instance_stats(instance_id)
                recommendations.append({
                    'instance_id': instance_id,
                    'reason': reason.value,
                    'stats': stats
                })
        
        return {
            'total_instances': len(self.instance_creation_time),
            'recommendations': recommendations,
            'should_rotate_count': len(recommendations)
        }