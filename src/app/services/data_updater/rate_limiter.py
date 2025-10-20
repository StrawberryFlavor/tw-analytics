"""
速率限制和间隔控制器

遵循单一职责原则，专门管理API请求的速率和间隔控制
防止触发Twitter API或其他服务的限制
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from collections import deque
import math


@dataclass
class RequestRecord:
    """请求记录 - 用于追踪请求历史"""
    timestamp: float
    success: bool
    response_time: float = 0.0
    error_type: Optional[str] = None


class RateLimiter:
    """速率限制器 - 单一职责原则"""
    
    def __init__(self, 
                 requests_per_minute: int = 30,
                 requests_per_hour: int = 1000,
                 base_delay: float = 2.0,
                 max_delay: float = 60.0):
        """
        初始化速率限制器
        
        Args:
            requests_per_minute: 每分钟最大请求数
            requests_per_hour: 每小时最大请求数  
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.base_delay = base_delay
        self.max_delay = max_delay
        
        # 请求历史记录（使用deque提高性能）
        self._minute_requests: deque = deque()
        self._hour_requests: deque = deque()
        
        # 自适应延迟控制
        self._consecutive_failures = 0
        self._success_count = 0
        self._last_request_time = 0.0
        
        self.logger = logging.getLogger(__name__)
        
    def _cleanup_old_requests(self):
        """清理过期的请求记录 - 保持数据结构精简"""
        current_time = time.time()
        
        # 清理1分钟前的记录
        while self._minute_requests and current_time - self._minute_requests[0].timestamp > 60:
            self._minute_requests.popleft()
        
        # 清理1小时前的记录
        while self._hour_requests and current_time - self._hour_requests[0].timestamp > 3600:
            self._hour_requests.popleft()
    
    def _is_rate_limited(self) -> tuple[bool, str]:
        """检查是否触发速率限制"""
        self._cleanup_old_requests()
        
        # 检查分钟级限制
        if len(self._minute_requests) >= self.requests_per_minute:
            return True, f"分钟级限制：{len(self._minute_requests)}/{self.requests_per_minute}"
        
        # 检查小时级限制
        if len(self._hour_requests) >= self.requests_per_hour:
            return True, f"小时级限制：{len(self._hour_requests)}/{self.requests_per_hour}"
        
        return False, ""
    
    def _calculate_adaptive_delay(self) -> float:
        """计算自适应延迟 - 基于成功/失败率"""
        # 基础延迟
        delay = self.base_delay
        
        # 基于连续失败次数增加延迟
        if self._consecutive_failures > 0:
            # 指数退避
            failure_multiplier = min(2 ** self._consecutive_failures, 8)  # 最大8倍
            delay *= failure_multiplier
            self.logger.debug(f"连续失败 {self._consecutive_failures} 次，延迟增加到 {delay:.1f}s")
        
        # 基于整体成功率调整
        total_requests = len(self._hour_requests)
        if total_requests >= 10:  # 有足够样本时
            success_requests = sum(1 for r in self._hour_requests if r.success)
            success_rate = success_requests / total_requests
            
            if success_rate < 0.8:  # 成功率低于80%
                delay *= 1.5
                self.logger.debug(f"成功率较低 ({success_rate:.1%})，延迟增加到 {delay:.1f}s")
        
        # 基于速率限制动态调整
        minute_usage = len(self._minute_requests) / self.requests_per_minute
        if minute_usage > 0.8:  # 使用率超过80%
            delay *= (1 + minute_usage)
            self.logger.debug(f"分钟使用率较高 ({minute_usage:.1%})，延迟调整到 {delay:.1f}s")
        
        return min(delay, self.max_delay)
    
    async def wait_if_needed(self) -> Dict[str, Any]:
        """如果需要，等待适当的时间间隔"""
        current_time = time.time()
        
        # 检查速率限制
        is_limited, limit_reason = self._is_rate_limited()
        
        # 计算需要等待的时间
        wait_time = 0.0
        wait_reasons = []
        
        # 1. 基础间隔控制
        if self._last_request_time > 0:
            time_since_last = current_time - self._last_request_time
            adaptive_delay = self._calculate_adaptive_delay()
            
            if time_since_last < adaptive_delay:
                base_wait = adaptive_delay - time_since_last
                wait_time = max(wait_time, base_wait)
                wait_reasons.append(f"基础间隔 ({adaptive_delay:.1f}s)")
        
        # 2. 速率限制等待
        if is_limited:
            # 等到最早的请求过期 + 一点缓冲
            if limit_reason.startswith("分钟"):
                oldest_time = self._minute_requests[0].timestamp
                rate_wait = 61 - (current_time - oldest_time)  # 等到过1分钟 + 1秒缓冲
            else:  # 小时限制
                oldest_time = self._hour_requests[0].timestamp
                rate_wait = 3601 - (current_time - oldest_time)  # 等到过1小时 + 1秒缓冲
            
            if rate_wait > 0:
                wait_time = max(wait_time, rate_wait)
                wait_reasons.append(f"速率限制 ({limit_reason})")
        
        # 执行等待
        if wait_time > 0:
            self.logger.info(f"⏳ 等待 {wait_time:.1f}s - 原因: {', '.join(wait_reasons)}")
            await asyncio.sleep(wait_time)
        
        # 更新最后请求时间
        self._last_request_time = time.time()
        
        return {
            'waited': wait_time > 0,
            'wait_time': wait_time,
            'wait_reasons': wait_reasons,
            'rate_limited': is_limited,
            'limit_reason': limit_reason if is_limited else None
        }
    
    def record_request(self, success: bool, response_time: float = 0.0, error_type: str = None):
        """记录请求结果 - 用于自适应控制"""
        current_time = time.time()
        
        record = RequestRecord(
            timestamp=current_time,
            success=success,
            response_time=response_time,
            error_type=error_type
        )
        
        # 添加到历史记录
        self._minute_requests.append(record)
        self._hour_requests.append(record)
        
        # 更新统计
        if success:
            self._consecutive_failures = 0
            self._success_count += 1
        else:
            self._consecutive_failures += 1
            self.logger.warning(f"请求失败 (连续 {self._consecutive_failures} 次): {error_type}")
        
        # 清理过期记录
        self._cleanup_old_requests()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取速率限制统计信息"""
        self._cleanup_old_requests()
        
        current_time = time.time()
        
        # 计算成功率
        minute_total = len(self._minute_requests)
        minute_success = sum(1 for r in self._minute_requests if r.success)
        minute_success_rate = minute_success / minute_total if minute_total > 0 else 1.0
        
        hour_total = len(self._hour_requests)
        hour_success = sum(1 for r in self._hour_requests if r.success)
        hour_success_rate = hour_success / hour_total if hour_total > 0 else 1.0
        
        # 计算平均响应时间
        if self._hour_requests:
            avg_response_time = sum(r.response_time for r in self._hour_requests) / len(self._hour_requests)
        else:
            avg_response_time = 0.0
        
        return {
            'current_time': current_time,
            'requests_per_minute': {
                'limit': self.requests_per_minute,
                'used': minute_total,
                'remaining': max(0, self.requests_per_minute - minute_total),
                'usage_percentage': (minute_total / self.requests_per_minute) * 100,
                'success_rate': minute_success_rate
            },
            'requests_per_hour': {
                'limit': self.requests_per_hour,
                'used': hour_total,
                'remaining': max(0, self.requests_per_hour - hour_total),
                'usage_percentage': (hour_total / self.requests_per_hour) * 100,
                'success_rate': hour_success_rate
            },
            'adaptive_control': {
                'consecutive_failures': self._consecutive_failures,
                'current_delay': self._calculate_adaptive_delay(),
                'base_delay': self.base_delay,
                'max_delay': self.max_delay
            },
            'performance': {
                'avg_response_time': avg_response_time,
                'total_success_count': self._success_count
            }
        }
    
    def reset_failure_count(self):
        """重置失败计数 - 用于手动恢复"""
        self._consecutive_failures = 0
        self.logger.info("失败计数已重置")
    
    def adjust_limits(self, requests_per_minute: int = None, requests_per_hour: int = None):
        """动态调整限制 - 开闭原则支持扩展"""
        if requests_per_minute is not None:
            self.requests_per_minute = requests_per_minute
            self.logger.info(f"分钟限制调整为: {requests_per_minute}")
        
        if requests_per_hour is not None:
            self.requests_per_hour = requests_per_hour
            self.logger.info(f"小时限制调整为: {requests_per_hour}")


class BatchRateLimiter(RateLimiter):
    """批处理速率限制器 - 里氏替换原则"""
    
    def __init__(self, 
                 requests_per_minute: int = 30,
                 requests_per_hour: int = 1000,
                 base_delay: float = 2.0,
                 batch_delay: float = 5.0,
                 max_delay: float = 60.0):
        super().__init__(requests_per_minute, requests_per_hour, base_delay, max_delay)
        self.batch_delay = batch_delay
        self._last_batch_time = 0.0
    
    async def wait_for_batch(self) -> Dict[str, Any]:
        """批次间的等待控制"""
        current_time = time.time()
        
        if self._last_batch_time > 0:
            time_since_batch = current_time - self._last_batch_time
            
            if time_since_batch < self.batch_delay:
                wait_time = self.batch_delay - time_since_batch
                self.logger.info(f"⏳ 批次间等待 {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        self._last_batch_time = time.time()
        
        return {
            'batch_waited': True,
            'batch_delay': self.batch_delay
        }


# 创建全局实例
_default_rate_limiter = None
_batch_rate_limiter = None

def get_rate_limiter() -> RateLimiter:
    """获取默认速率限制器单例"""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = RateLimiter()
    return _default_rate_limiter

def get_batch_rate_limiter() -> BatchRateLimiter:
    """获取批处理速率限制器单例"""
    global _batch_rate_limiter
    if _batch_rate_limiter is None:
        _batch_rate_limiter = BatchRateLimiter()
    return _batch_rate_limiter