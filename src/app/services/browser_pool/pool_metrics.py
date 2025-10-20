"""
浏览器池统计管理器
负责收集和管理池的各种统计指标
"""

import time
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class PoolMetrics:
    """池统计指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    pool_hits: int = 0
    pool_misses: int = 0
    start_time: float = 0.0
    
    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()


class PoolMetricsManager:
    """
    浏览器池统计管理器
    
    职责：
    - 收集池的各种统计指标
    - 提供统计数据的查询接口
    - 计算衍生指标（成功率、命中率等）
    """
    
    def __init__(self):
        self.metrics = PoolMetrics()
    
    def record_request_start(self):
        """记录请求开始"""
        self.metrics.total_requests += 1
    
    def record_pool_hit(self):
        """记录池命中"""
        self.metrics.pool_hits += 1
    
    def record_pool_miss(self):
        """记录池未命中（需要创建新实例）"""
        self.metrics.pool_misses += 1
    
    def record_request_success(self):
        """记录请求成功"""
        self.metrics.successful_requests += 1
    
    def record_request_failure(self):
        """记录请求失败"""
        self.metrics.failed_requests += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_requests': self.metrics.total_requests,
            'successful_requests': self.metrics.successful_requests,
            'failed_requests': self.metrics.failed_requests,
            'success_rate': self._calculate_success_rate(),
            'pool_hits': self.metrics.pool_hits,
            'pool_misses': self.metrics.pool_misses,
            'pool_hit_rate': self._calculate_hit_rate(),
            'uptime_seconds': time.time() - self.metrics.start_time
        }
    
    def _calculate_success_rate(self) -> float:
        """计算成功率"""
        if self.metrics.total_requests == 0:
            return 0.0
        return self.metrics.successful_requests / self.metrics.total_requests
    
    def _calculate_hit_rate(self) -> float:
        """计算池命中率"""
        if self.metrics.total_requests == 0:
            return 0.0
        return self.metrics.pool_hits / self.metrics.total_requests
    
    def reset_statistics(self):
        """重置统计信息"""
        self.metrics = PoolMetrics()
    
    def get_summary_text(self) -> str:
        """获取统计摘要文本"""
        stats = self.get_statistics()
        return (
            f"总请求: {stats['total_requests']}, "
            f"成功率: {stats['success_rate']:.1%}, "
            f"池命中率: {stats['pool_hit_rate']:.1%}"
        )