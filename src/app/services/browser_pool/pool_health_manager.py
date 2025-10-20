"""
浏览器池健康检查管理器
负责监控池中实例的健康状态，自动移除不健康的实例
"""

import asyncio
import logging
from typing import List, Callable, Optional

from .browser_instance import PooledBrowserInstance


class PoolHealthManager:
    """
    浏览器池健康检查管理器
    
    职责：
    - 周期性健康检查
    - 移除不健康实例
    - 补充实例到最小数量
    - 管理后台健康检查任务
    """
    
    def __init__(self, 
                 health_check_interval: float = 60.0,
                 min_pool_size: int = 2,
                 instance_creator: Optional[Callable] = None,
                 instance_disposer: Optional[Callable] = None):
        """
        初始化健康检查管理器
        
        Args:
            health_check_interval: 健康检查间隔（秒）
            min_pool_size: 最小池大小
            instance_creator: 实例创建函数
            instance_disposer: 实例销毁函数
        """
        self.health_check_interval = health_check_interval
        self.min_pool_size = min_pool_size
        self.instance_creator = instance_creator
        self.instance_disposer = instance_disposer
        
        self._health_check_task: Optional[asyncio.Task] = None
        self._disposing = False
        self.logger = logging.getLogger(__name__)
    
    def start_health_monitoring(self):
        """启动健康检查监控"""
        if self._health_check_task and not self._health_check_task.done():
            self.logger.warning("健康检查任务已在运行")
            return
            
        self._disposing = False
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self.logger.info(f"健康检查监控已启动，间隔: {self.health_check_interval}秒")
    
    def stop_health_monitoring(self):
        """停止健康检查监控"""
        self._disposing = True
        if self._health_check_task:
            self._health_check_task.cancel()
            self.logger.info("健康检查监控已停止")
    
    async def wait_for_health_monitoring_stop(self):
        """等待健康检查任务完全停止"""
        if self._health_check_task:
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
    
    async def perform_health_check(self, instances: List[PooledBrowserInstance]) -> dict:
        """
        执行健康检查
        
        Args:
            instances: 实例列表（会被修改）
            
        Returns:
            健康检查结果
        """
        if not instances:
            return {'checked': 0, 'unhealthy': 0, 'removed': 0, 'created': 0}
        
        unhealthy_instances = []
        
        # 检查所有实例的健康状态
        for instance in instances[:]:  # 使用切片复制避免修改时出错
            try:
                if not await instance.health_check():
                    unhealthy_instances.append(instance)
                    self.logger.warning(f"发现不健康实例: {instance.instance_id}")
            except Exception as e:
                self.logger.error(f"健康检查实例 {instance.instance_id} 时出错: {e}")
                unhealthy_instances.append(instance)
        
        # 移除不健康的实例
        removed_count = 0
        for instance in unhealthy_instances:
            try:
                instances.remove(instance)
                removed_count += 1
                self.logger.info(f"移除不健康实例: {instance.instance_id}")
                
                # 异步销毁实例
                if self.instance_disposer:
                    asyncio.create_task(self.instance_disposer(instance))
                else:
                    asyncio.create_task(instance.dispose())
                    
            except ValueError:
                # 实例已被移除
                pass
            except Exception as e:
                self.logger.error(f"移除实例 {instance.instance_id} 时出错: {e}")
        
        # 确保最小池大小
        created_count = 0
        while len(instances) < self.min_pool_size:
            try:
                if self.instance_creator:
                    new_instance = await self.instance_creator()
                    instances.append(new_instance)
                    created_count += 1
                    self.logger.info(f"健康检查中补充实例: {new_instance.instance_id}")
                else:
                    self.logger.warning("无法补充实例：未提供实例创建函数")
                    break
            except Exception as e:
                self.logger.error(f"健康检查中创建实例失败: {e}")
                break
        
        result = {
            'checked': len(instances) + len(unhealthy_instances),
            'unhealthy': len(unhealthy_instances),
            'removed': removed_count,
            'created': created_count
        }
        
        if result['unhealthy'] > 0 or result['created'] > 0:
            self.logger.info(f"健康检查完成: {result}")
        
        return result
    
    async def _health_check_loop(self):
        """健康检查循环"""
        self.logger.info("健康检查循环启动")
        
        while not self._disposing:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # 通过回调函数执行健康检查
                if hasattr(self, '_health_check_callback') and self._health_check_callback:
                    await self._health_check_callback()
                
            except asyncio.CancelledError:
                self.logger.info("健康检查循环被取消")
                break
            except Exception as e:
                self.logger.error(f"健康检查循环出错: {e}")
                # 继续运行，不因为单次错误而停止
    
    def set_health_check_callback(self, callback):
        """设置健康检查回调函数"""
        self._health_check_callback = callback
    
    def get_health_manager_info(self) -> dict:
        """获取健康管理器信息"""
        return {
            'health_check_interval': self.health_check_interval,
            'min_pool_size': self.min_pool_size,
            'is_monitoring': self._health_check_task is not None and not self._health_check_task.done(),
            'disposing': self._disposing
        }