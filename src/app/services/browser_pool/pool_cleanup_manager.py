"""
浏览器池清理管理器
负责清理空闲时间过长的实例，维护池的健康状态
"""

import asyncio
import logging
from typing import List, Optional, Callable

from .browser_instance import PooledBrowserInstance


class PoolCleanupManager:
    """
    浏览器池清理管理器
    
    职责：
    - 周期性清理空闲实例
    - 维护池的最小大小
    - 管理后台清理任务
    - 提供手动清理接口
    """
    
    def __init__(self, 
                 max_idle_time: float = 300.0,
                 min_pool_size: int = 2,
                 cleanup_interval: float = None,
                 instance_disposer: Optional[Callable] = None):
        """
        初始化清理管理器
        
        Args:
            max_idle_time: 最大空闲时间（秒）
            min_pool_size: 最小池大小
            cleanup_interval: 清理检查间隔（默认为max_idle_time/4）
            instance_disposer: 实例销毁函数
        """
        self.max_idle_time = max_idle_time
        self.min_pool_size = min_pool_size
        self.cleanup_interval = cleanup_interval or (max_idle_time / 4)
        self.instance_disposer = instance_disposer
        
        self._cleanup_task: Optional[asyncio.Task] = None
        self._disposing = False
        self.logger = logging.getLogger(__name__)
    
    def start_cleanup_monitoring(self):
        """启动清理监控"""
        if self._cleanup_task and not self._cleanup_task.done():
            self.logger.warning("清理任务已在运行")
            return
            
        self._disposing = False
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info(f"清理监控已启动，间隔: {self.cleanup_interval:.1f}秒，最大空闲: {self.max_idle_time:.1f}秒")
    
    def stop_cleanup_monitoring(self):
        """停止清理监控"""
        self._disposing = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self.logger.info("清理监控已停止")
    
    async def wait_for_cleanup_stop(self):
        """等待清理任务完全停止"""
        if self._cleanup_task:
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def cleanup_idle_instances(self, instances: List[PooledBrowserInstance]) -> dict:
        """
        清理空闲时间过长的实例
        
        Args:
            instances: 实例列表（会被修改）
            
        Returns:
            清理结果统计
        """
        if len(instances) <= self.min_pool_size:
            # 已经是最小池大小，不清理
            return {'checked': len(instances), 'idle': 0, 'removed': 0}
        
        idle_instances = []
        
        # 查找需要清理的实例（空闲过久或ERROR状态）
        for instance in instances:
            if instance.is_idle_too_long(self.max_idle_time):
                idle_instances.append(instance)
                self.logger.debug(f"发现空闲过久实例: {instance.instance_id}")
            elif hasattr(instance, 'status') and instance.status.value == 'error':
                idle_instances.append(instance)
                self.logger.warning(f"发现ERROR状态实例: {instance.instance_id}，需要清理")
            elif instance.usage_count > 30:
                idle_instances.append(instance)
                self.logger.warning(f"发现过度使用实例: {instance.instance_id} (使用次数: {instance.usage_count})，需要清理")
        
        if not idle_instances:
            return {'checked': len(instances), 'idle': 0, 'removed': 0}
        
        # 计算可以移除的实例数量（保留最小池大小）
        current_size = len(instances)
        idle_count = len(idle_instances)
        max_removable = current_size - self.min_pool_size
        actual_remove_count = min(idle_count, max_removable)
        
        if actual_remove_count <= 0:
            self.logger.debug(f"发现{idle_count}个空闲实例，但需保持最小池大小{self.min_pool_size}，跳过清理")
            return {'checked': current_size, 'idle': idle_count, 'removed': 0}
        
        # 移除空闲实例（优先移除空闲时间最长的）
        idle_instances.sort(key=lambda x: x.last_used_at)  # 按最后使用时间排序
        instances_to_remove = idle_instances[:actual_remove_count]
        
        removed_count = 0
        for instance in instances_to_remove:
            try:
                instances.remove(instance)
                removed_count += 1
                self.logger.info(f"清理空闲实例: {instance.instance_id} (空闲: {instance.last_used_at:.1f}s)")
                
                # 异步销毁实例
                if self.instance_disposer:
                    asyncio.create_task(self.instance_disposer(instance))
                else:
                    asyncio.create_task(instance.dispose())
                    
            except ValueError:
                # 实例已被移除
                pass
            except Exception as e:
                self.logger.error(f"清理实例 {instance.instance_id} 时出错: {e}")
        
        result = {
            'checked': current_size,
            'idle': idle_count,
            'removed': removed_count
        }
        
        if removed_count > 0:
            self.logger.info(f"清理完成: 检查{current_size}个实例，发现{idle_count}个空闲，移除{removed_count}个")
        
        return result
    
    async def force_cleanup(self, instances: List[PooledBrowserInstance], 
                           target_size: int = None) -> dict:
        """
        强制清理到指定大小
        
        Args:
            instances: 实例列表（会被修改）
            target_size: 目标大小（默认为min_pool_size）
            
        Returns:
            清理结果统计
        """
        target_size = target_size or self.min_pool_size
        current_size = len(instances)
        
        if current_size <= target_size:
            return {'checked': current_size, 'target': target_size, 'removed': 0}
        
        # 优先移除空闲实例
        idle_instances = [inst for inst in instances if inst.is_idle_too_long(0)]  # 所有空闲实例
        
        # 如果空闲实例不够，选择最久未使用的实例
        if len(idle_instances) < (current_size - target_size):
            all_instances = sorted(instances, key=lambda x: x.last_used_at)
            instances_to_remove = all_instances[:current_size - target_size]
        else:
            instances_to_remove = idle_instances[:current_size - target_size]
        
        removed_count = 0
        for instance in instances_to_remove:
            try:
                instances.remove(instance)
                removed_count += 1
                self.logger.info(f"强制清理实例: {instance.instance_id}")
                
                # 异步销毁实例
                if self.instance_disposer:
                    asyncio.create_task(self.instance_disposer(instance))
                else:
                    asyncio.create_task(instance.dispose())
                    
            except ValueError:
                pass
            except Exception as e:
                self.logger.error(f"强制清理实例 {instance.instance_id} 时出错: {e}")
        
        result = {
            'checked': current_size,
            'target': target_size,
            'removed': removed_count
        }
        
        self.logger.info(f"强制清理完成: {current_size} -> {len(instances)} 实例")
        return result
    
    async def _cleanup_loop(self):
        """清理循环"""
        self.logger.info("清理循环启动")
        
        while not self._disposing:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                # 通过回调函数执行清理
                if hasattr(self, '_cleanup_callback') and self._cleanup_callback:
                    await self._cleanup_callback()
                
            except asyncio.CancelledError:
                self.logger.info("清理循环被取消")
                break
            except Exception as e:
                self.logger.error(f"清理循环出错: {e}")
                # 继续运行，不因为单次错误而停止
    
    def set_cleanup_callback(self, callback):
        """设置清理回调函数"""
        self._cleanup_callback = callback
    
    def get_cleanup_manager_info(self) -> dict:
        """获取清理管理器信息"""
        return {
            'max_idle_time': self.max_idle_time,
            'min_pool_size': self.min_pool_size,
            'cleanup_interval': self.cleanup_interval,
            'is_monitoring': self._cleanup_task is not None and not self._cleanup_task.done(),
            'disposing': self._disposing
        }