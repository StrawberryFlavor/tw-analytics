"""
浏览器实例选择器
负责实现不同的实例选择策略（轮询、随机等）
"""

import logging
from typing import List, Optional
from enum import Enum

from .browser_instance import PooledBrowserInstance


class SelectionStrategy(Enum):
    """选择策略"""
    ROUND_ROBIN = "round_robin"  # 轮询
    RANDOM = "random"           # 随机
    LEAST_USED = "least_used"   # 最少使用


class InstanceSelector:
    """
    浏览器实例选择器
    
    职责：
    - 实现不同的实例选择策略
    - 维护选择状态（如轮询索引）
    - 提供负载均衡功能
    """
    
    def __init__(self, strategy: SelectionStrategy = SelectionStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self._round_robin_index = 0
        self.logger = logging.getLogger(__name__)
    
    def find_available_instance(self, instances: List[PooledBrowserInstance]) -> Optional[PooledBrowserInstance]:
        """
        根据策略查找可用实例
        
        Args:
            instances: 实例列表
            
        Returns:
            可用实例或None
        """
        if not instances:
            return None
            
        if self.strategy == SelectionStrategy.ROUND_ROBIN:
            return self._find_round_robin(instances)
        elif self.strategy == SelectionStrategy.RANDOM:
            return self._find_random(instances)
        elif self.strategy == SelectionStrategy.LEAST_USED:
            return self._find_least_used(instances)
        else:
            # 默认使用轮询
            return self._find_round_robin(instances)
    
    def _find_round_robin(self, instances: List[PooledBrowserInstance]) -> Optional[PooledBrowserInstance]:
        """
        使用轮询算法查找可用实例（负载均衡）
        """
        total_instances = len(instances)
        self.logger.info(f"开始轮询查找可用实例（总数: {total_instances}, 从索引 {self._round_robin_index} 开始）")
        
        # 打印所有实例状态
        for i, inst in enumerate(instances):
            status_icon = "" if inst.is_available() else ""
            status_text = getattr(inst, 'status', None)
            status_display = status_text.value if hasattr(status_text, 'value') else str(status_text)
            self.logger.debug(f"  实例[{i}] {inst.instance_id}: 状态={status_display}, 使用次数={inst.usage_count}")
        
        # 从上次的位置开始轮询
        for attempt in range(total_instances):
            index = (self._round_robin_index + attempt) % total_instances
            instance = instances[index]
            
            self.logger.debug(f"  检查实例[{index}]: {instance.instance_id}, 可用: {instance.is_available()}")
            
            if instance.is_available():
                # 更新下次轮询的起始位置
                self._round_robin_index = (index + 1) % total_instances
                self.logger.info(f"轮询选中实例[{index}]: {instance.instance_id} (使用次数: {instance.usage_count}, 下次从 {self._round_robin_index} 开始)")
                return instance
        
        self.logger.debug("轮询完成，没有找到可用实例")
        return None
    
    def _find_random(self, instances: List[PooledBrowserInstance]) -> Optional[PooledBrowserInstance]:
        """随机选择可用实例"""
        import random
        
        available_instances = [inst for inst in instances if inst.is_available()]
        if not available_instances:
            return None
            
        selected = random.choice(available_instances)
        self.logger.info(f"随机选中实例: {selected.instance_id}")
        return selected
    
    def _find_least_used(self, instances: List[PooledBrowserInstance]) -> Optional[PooledBrowserInstance]:
        """选择使用次数最少的可用实例"""
        available_instances = [inst for inst in instances if inst.is_available()]
        if not available_instances:
            return None
            
        # 按使用次数排序，选择最少的
        selected = min(available_instances, key=lambda x: x.usage_count)
        self.logger.info(f"选中最少使用实例: {selected.instance_id} (使用次数: {selected.usage_count})")
        return selected
    
    def reset_state(self):
        """重置选择器状态"""
        self._round_robin_index = 0
    
    def get_selection_info(self) -> dict:
        """获取选择器信息"""
        return {
            'strategy': self.strategy.value,
            'round_robin_index': self._round_robin_index
        }
