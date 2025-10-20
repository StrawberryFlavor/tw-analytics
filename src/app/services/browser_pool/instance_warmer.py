"""
浏览器实例预热管理器
负责实例的预热操作，提升首次使用性能
"""

import asyncio
import logging
from typing import List

from .browser_instance import PooledBrowserInstance


class InstanceWarmer:
    """
    浏览器实例预热管理器
    
    职责：
    - 预热单个或批量实例
    - 执行基本的实例健康检查
    - 提供不同的预热策略
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def warmup_instance(self, instance: PooledBrowserInstance, timeout: float = 15.0) -> bool:
        """
        预热浏览器实例
        
        Args:
            instance: 要预热的实例
            timeout: 超时时间（秒）
            
        Returns:
            预热是否成功
        """
        try:
            self.logger.info(f"开始预热浏览器实例: {instance.instance_id}")
            
            # 获取实例进行预热
            context, page = await asyncio.wait_for(
                instance.acquire(), 
                timeout=timeout
            )
            
            # 执行基本预热检查
            await self._perform_warmup_checks(context, page)
            
            # 释放实例
            await instance.release()
            
            self.logger.info(f"浏览器实例预热成功: {instance.instance_id}")
            return True
            
        except asyncio.TimeoutError:
            self.logger.warning(f"浏览器实例预热超时，跳过预热: {instance.instance_id}")
            return False
        except Exception as e:
            self.logger.warning(f"浏览器实例预热失败，跳过预热: {instance.instance_id}, 错误: {e}")
            return False
    
    async def batch_warmup(self, instances: List[PooledBrowserInstance], 
                          max_concurrent: int = 3, timeout: float = 15.0) -> dict:
        """
        批量预热实例
        
        Args:
            instances: 实例列表
            max_concurrent: 最大并发预热数
            timeout: 单个实例超时时间
            
        Returns:
            预热结果统计
        """
        if not instances:
            return {'total': 0, 'success': 0, 'failed': 0}
        
        self.logger.info(f"开始批量预热 {len(instances)} 个实例 (最大并发: {max_concurrent})")
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def warmup_with_semaphore(inst):
            async with semaphore:
                return await self.warmup_instance(inst, timeout)
        
        # 并发执行预热
        results = await asyncio.gather(
            *[warmup_with_semaphore(inst) for inst in instances],
            return_exceptions=True
        )
        
        # 统计结果
        success_count = sum(1 for r in results if r is True)
        failed_count = len(results) - success_count
        
        result = {
            'total': len(instances),
            'success': success_count,
            'failed': failed_count
        }
        
        self.logger.info(f"批量预热完成: {result}")
        return result
    
    async def _perform_warmup_checks(self, context, page):
        """
        执行预热检查
        
        Args:
            context: 浏览器上下文
            page: 页面对象
        """
        # 执行基本预热检查
        _ = context, page  # 明确标记变量未直接使用
        
        # 可以在这里添加更多预热操作，比如：
        # - 设置基本的页面选项
        # - 执行JavaScript检查
        # - 加载必要的资源
        
        # 目前只做基本的可用性检查
        await page.evaluate("() => true")
    
    def get_warmer_info(self) -> dict:
        """获取预热管理器信息"""
        return {
            'warmer_type': 'basic',
            'supports_batch': True,
            'supports_concurrent': True
        }