"""
Cookie管理器 - 简洁高效
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any
from ..core.path_manager import get_cookie_file_path


class CookieManager:
    """Cookie管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cookie_file = get_cookie_file_path()
        self._cached_cookies = None
        
    async def get_valid_cookies(self) -> Optional[List[Dict[str, Any]]]:
        """获取cookies - 简单直接"""
        # 如果有缓存，直接返回
        if self._cached_cookies:
            return self._cached_cookies
            
        # 从文件加载
        cookies = self._load_from_file()
        if cookies:
            self._cached_cookies = cookies
            self.logger.info(f"Loaded {len(cookies)} cookies from file")
        else:
            self.logger.warning("No cookies found in file")
            
        return cookies
    
    def _load_from_file(self) -> Optional[List[Dict[str, Any]]]:
        """从文件加载cookies"""
        if not os.path.exists(self.cookie_file):
            return None
            
        try:
            with open(self.cookie_file, 'r') as f:
                cookies = json.load(f)
                return cookies if isinstance(cookies, list) else None
        except Exception as e:
            self.logger.error(f"Failed to load cookies: {e}")
            return None
    
    def save_cookies(self, cookies: List[Dict[str, Any]]):
        """保存cookies到文件"""
        try:
            os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
            with open(self.cookie_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            self._cached_cookies = cookies
            self.logger.info(f"Saved {len(cookies)} cookies to file")
        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")
    
    def clear_cache(self):
        """清除缓存的cookies"""
        self._cached_cookies = None
        self.logger.info("Cleared cookie cache")
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        has_file = os.path.exists(self.cookie_file)
        has_cache = self._cached_cookies is not None
        
        return {
            "has_cookie_file": has_file,
            "has_cached_cookies": has_cache,
            "cookie_count": len(self._cached_cookies) if has_cache else 0
        }


# 单例实例
_cookie_manager = None


def get_cookie_manager() -> CookieManager:
    """获取Cookie管理器单例"""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager