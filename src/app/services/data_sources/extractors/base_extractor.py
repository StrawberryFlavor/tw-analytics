"""
基础提取器类
"""

import logging
from typing import Dict, Any, Optional
from playwright.async_api import Page, Locator


class BaseExtractor:
    """基础提取器类，提供共同的功能和接口"""
    
    def __init__(self, page: Page):
        self.page = page
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _is_reasonable_metric_value(self, value: int) -> bool:
        """验证指标值是否合理"""
        return 0 <= value <= 10_000_000_000  # 100亿的上限
    
    def _validate_and_clean_metrics(self, metrics: Dict[str, int]):
        """验证和清理指标数据"""
        for key in list(metrics.keys()):
            if not self._is_reasonable_metric_value(metrics[key]):
                self.logger.warning(f"Removing unreasonable {key} value: {metrics[key]}")
                metrics[key] = 0
        
        # 确保基本字段存在
        for field in ['likes', 'retweets', 'replies', 'quotes', 'views']:
            if field not in metrics:
                metrics[field] = 0
    
    async def _safe_extract(self, extraction_func, *args, **kwargs):
        """安全执行提取操作，捕获异常"""
        try:
            return await extraction_func(*args, **kwargs)
        except Exception as e:
            self.logger.debug(f"Error in {extraction_func.__name__}: {e}")
            return None