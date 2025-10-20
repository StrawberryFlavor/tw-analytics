"""
浏览器池恢复管理器
处理各种故障场景和自动恢复策略
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass

from .browser_instance import PooledBrowserInstance, InstanceStatus


class FailureType(Enum):
    """故障类型"""
    BROWSER_CRASH = "browser_crash"          # 浏览器崩溃
    NETWORK_ERROR = "network_error"          # 网络错误
    TIMEOUT_ERROR = "timeout_error"          # 超时错误
    ANTI_BOT_DETECTION = "anti_bot"          # 反爬虫检测
    PROXY_ERROR = "proxy_error"              # 代理错误
    MEMORY_ERROR = "memory_error"            # 内存不足
    UNKNOWN_ERROR = "unknown_error"          # 未知错误


class RecoveryAction(Enum):
    """恢复动作"""
    RESTART_INSTANCE = "restart_instance"    # 重启实例
    REPLACE_INSTANCE = "replace_instance"    # 替换实例
    DELAY_AND_RETRY = "delay_and_retry"      # 延时重试
    CIRCUIT_BREAK = "circuit_break"          # 熔断
    SCALE_DOWN = "scale_down"                # 缩容
    SCALE_UP = "scale_up"                    # 扩容


@dataclass
class FailureRecord:
    """故障记录"""
    instance_id: str
    failure_type: FailureType
    timestamp: float
    error_message: str
    recovery_action: Optional[RecoveryAction] = None
    recovered: bool = False


class RecoveryManager:
    """
    浏览器池恢复管理器
    
    负责监控故障、分析故障模式并执行恢复策略
    """
    
    def __init__(self, browser_pool):
        self.browser_pool = browser_pool
        self.logger = logging.getLogger(__name__)
        
        # 故障记录
        self.failure_history: List[FailureRecord] = []
        self.failure_counts: Dict[FailureType, int] = {}
        self.instance_failure_counts: Dict[str, int] = {}
        
        # 恢复策略配置
        self.max_instance_failures = 3          # 单实例最大故障次数
        self.failure_time_window = 300.0        # 故障时间窗口（秒）
        self.circuit_break_threshold = 5        # 熔断阈值
        self.circuit_break_duration = 60.0      # 熔断持续时间
        
        # 恢复状态
        self.circuit_broken = False
        self.circuit_break_start = 0.0
        self.last_recovery_time = 0.0
        
        # 自适应参数
        self.dynamic_timeout = 30.0             # 动态超时时间
        self.adaptive_retry_delay = 2.0         # 自适应重试延时
    
    async def handle_failure(self, instance: PooledBrowserInstance, error: Exception) -> RecoveryAction:
        """
        处理故障
        
        Args:
            instance: 故障实例
            error: 错误信息
            
        Returns:
            恢复动作
        """
        failure_type = self._classify_failure(error)
        
        # 记录故障
        failure_record = FailureRecord(
            instance_id=instance.instance_id,
            failure_type=failure_type,
            timestamp=time.time(),
            error_message=str(error)
        )
        
        self.failure_history.append(failure_record)
        self.failure_counts[failure_type] = self.failure_counts.get(failure_type, 0) + 1
        self.instance_failure_counts[instance.instance_id] = self.instance_failure_counts.get(instance.instance_id, 0) + 1
        
        self.logger.warning(f"实例 {instance.instance_id} 发生故障: {failure_type.value} - {error}")
        
        # 决定恢复策略
        recovery_action = await self._decide_recovery_action(instance, failure_type)
        failure_record.recovery_action = recovery_action
        
        # 执行恢复动作
        await self._execute_recovery_action(instance, recovery_action, failure_record)
        
        # 更新自适应参数
        self._update_adaptive_parameters(failure_type)
        
        return recovery_action
    
    def _classify_failure(self, error: Exception) -> FailureType:
        """分类故障类型"""
        error_str = str(error).lower()
        
        if 'timeout' in error_str or 'time out' in error_str:
            return FailureType.TIMEOUT_ERROR
        elif 'network' in error_str or 'connection' in error_str:
            return FailureType.NETWORK_ERROR
        elif 'proxy' in error_str:
            return FailureType.PROXY_ERROR
        elif 'browser' in error_str and ('crash' in error_str or 'closed' in error_str):
            return FailureType.BROWSER_CRASH
        elif 'memory' in error_str or 'out of memory' in error_str:
            return FailureType.MEMORY_ERROR
        elif any(keyword in error_str for keyword in ['blocked', 'detected', 'captcha', 'rate limit']):
            return FailureType.ANTI_BOT_DETECTION
        else:
            return FailureType.UNKNOWN_ERROR
    
    async def _decide_recovery_action(self, instance: PooledBrowserInstance, failure_type: FailureType) -> RecoveryAction:
        """决定恢复策略"""
        
        # 检查熔断状态
        if self._should_circuit_break():
            self.circuit_broken = True
            self.circuit_break_start = time.time()
            return RecoveryAction.CIRCUIT_BREAK
        
        # 实例故障次数过多
        if self.instance_failure_counts.get(instance.instance_id, 0) >= self.max_instance_failures:
            return RecoveryAction.REPLACE_INSTANCE
        
        # 根据故障类型决定策略
        if failure_type == FailureType.BROWSER_CRASH:
            return RecoveryAction.RESTART_INSTANCE
        elif failure_type == FailureType.ANTI_BOT_DETECTION:
            return RecoveryAction.DELAY_AND_RETRY
        elif failure_type == FailureType.MEMORY_ERROR:
            return RecoveryAction.SCALE_DOWN
        elif failure_type == FailureType.NETWORK_ERROR:
            # 检查是否需要扩容以提供冗余
            if len(self.browser_pool.instances) < self.browser_pool.max_size:
                return RecoveryAction.SCALE_UP
            else:
                return RecoveryAction.RESTART_INSTANCE
        else:
            return RecoveryAction.RESTART_INSTANCE
    
    async def _execute_recovery_action(self, instance: PooledBrowserInstance, action: RecoveryAction, failure_record: FailureRecord):
        """执行恢复动作"""
        try:
            if action == RecoveryAction.RESTART_INSTANCE:
                await self._restart_instance(instance)
            elif action == RecoveryAction.REPLACE_INSTANCE:
                await self._replace_instance(instance)
            elif action == RecoveryAction.DELAY_AND_RETRY:
                await self._delay_and_retry(instance)
            elif action == RecoveryAction.CIRCUIT_BREAK:
                await self._circuit_break()
            elif action == RecoveryAction.SCALE_DOWN:
                await self._scale_down()
            elif action == RecoveryAction.SCALE_UP:
                await self._scale_up()
            
            failure_record.recovered = True
            self.last_recovery_time = time.time()
            self.logger.info(f"恢复动作 {action.value} 执行成功")
            
        except Exception as e:
            self.logger.error(f"执行恢复动作 {action.value} 失败: {e}")
            failure_record.recovered = False
    
    async def _restart_instance(self, instance: PooledBrowserInstance):
        """重启实例"""
        self.logger.info(f"重启实例: {instance.instance_id}")
        
        # 标记实例为初始化状态
        instance.status = InstanceStatus.INITIALIZING
        
        try:
            # 清理现有资源
            await instance.dispose()
            
            # 等待一小段时间
            await asyncio.sleep(1.0)
            
            # 重新创建浏览器实例（这里需要访问pool的创建方法）
            # 实际实现中可能需要重构以支持实例重启
            
        except Exception as e:
            instance.status = InstanceStatus.ERROR
            raise e
    
    async def _replace_instance(self, instance: PooledBrowserInstance):
        """替换实例"""
        self.logger.info(f"替换实例: {instance.instance_id}")
        
        async with self.browser_pool._lock:
            try:
                # 从池中移除故障实例
                if instance in self.browser_pool.instances:
                    self.browser_pool.instances.remove(instance)
                
                # 销毁故障实例
                await instance.dispose()
                
                # 创建新实例（如果池大小允许）
                if len(self.browser_pool.instances) < self.browser_pool.min_size:
                    new_instance = await self.browser_pool._create_browser_instance()
                    self.browser_pool.instances.append(new_instance)
                    self.logger.info(f"创建替换实例: {new_instance.instance_id}")
                
                # 清理失败计数
                self.instance_failure_counts.pop(instance.instance_id, None)
                
            except Exception as e:
                self.logger.error(f"替换实例失败: {e}")
                raise
    
    async def _delay_and_retry(self, instance: PooledBrowserInstance):
        """延时重试"""
        delay = self.adaptive_retry_delay
        self.logger.info(f"延时重试: {instance.instance_id}, 等待 {delay}s")
        
        # 增加延时以应对反爬虫检测
        await asyncio.sleep(delay)
        
        # 重置实例状态
        instance.status = InstanceStatus.IDLE
        instance.error_count = max(0, instance.error_count - 1)  # 减少错误计数
    
    async def _circuit_break(self):
        """熔断"""
        self.logger.warning(f"触发熔断，持续时间: {self.circuit_break_duration}s")
        
        # 暂停所有新请求处理
        # 在实际实现中，这里应该通知浏览器池停止接受新请求
        await asyncio.sleep(1.0)  # 短暂暂停
    
    async def _scale_down(self):
        """缩容"""
        async with self.browser_pool._lock:
            if len(self.browser_pool.instances) > self.browser_pool.min_size:
                # 找到空闲实例并移除
                for instance in self.browser_pool.instances[:]:
                    if instance.status == InstanceStatus.IDLE:
                        self.browser_pool.instances.remove(instance)
                        await instance.dispose()
                        self.logger.info(f"缩容移除实例: {instance.instance_id}")
                        break
    
    async def _scale_up(self):
        """扩容"""
        async with self.browser_pool._lock:
            if len(self.browser_pool.instances) < self.browser_pool.max_size:
                try:
                    new_instance = await self.browser_pool._create_browser_instance()
                    self.browser_pool.instances.append(new_instance)
                    self.logger.info(f"扩容创建实例: {new_instance.instance_id}")
                except Exception as e:
                    self.logger.error(f"扩容失败: {e}")
    
    def _should_circuit_break(self) -> bool:
        """判断是否应该熔断"""
        if self.circuit_broken:
            # 检查熔断是否应该恢复
            if time.time() - self.circuit_break_start > self.circuit_break_duration:
                self.circuit_broken = False
                self.logger.info("熔断恢复")
            return False
        
        # 检查最近故障频率
        recent_failures = [
            f for f in self.failure_history 
            if time.time() - f.timestamp < self.failure_time_window
        ]
        
        return len(recent_failures) >= self.circuit_break_threshold
    
    def _update_adaptive_parameters(self, failure_type: FailureType):
        """更新自适应参数"""
        if failure_type == FailureType.TIMEOUT_ERROR:
            # 增加超时时间
            self.dynamic_timeout = min(self.dynamic_timeout * 1.2, 60.0)
        elif failure_type == FailureType.ANTI_BOT_DETECTION:
            # 增加重试延时
            self.adaptive_retry_delay = min(self.adaptive_retry_delay * 1.5, 30.0)
        
        self.logger.debug(f"更新自适应参数 - 超时: {self.dynamic_timeout:.1f}s, 重试延时: {self.adaptive_retry_delay:.1f}s")
    
    def get_recovery_metrics(self) -> Dict[str, Any]:
        """获取恢复指标"""
        recent_failures = [
            f for f in self.failure_history 
            if time.time() - f.timestamp < self.failure_time_window
        ]
        
        recovery_rate = sum(1 for f in recent_failures if f.recovered) / max(1, len(recent_failures))
        
        return {
            'total_failures': len(self.failure_history),
            'recent_failures': len(recent_failures),
            'failure_types': dict(self.failure_counts),
            'recovery_rate': recovery_rate,
            'circuit_broken': self.circuit_broken,
            'adaptive_params': {
                'dynamic_timeout': self.dynamic_timeout,
                'adaptive_retry_delay': self.adaptive_retry_delay
            },
            'instance_failure_counts': dict(self.instance_failure_counts)
        }
    
    def reset_metrics(self):
        """重置指标"""
        self.failure_history.clear()
        self.failure_counts.clear()
        self.instance_failure_counts.clear()
        self.circuit_broken = False
        self.dynamic_timeout = 30.0
        self.adaptive_retry_delay = 2.0
        
        self.logger.info("恢复管理器指标已重置")