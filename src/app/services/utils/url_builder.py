"""
Twitter/X URL构建工具
统一管理平台URL的构建，避免硬编码
"""

import os
from typing import Optional
from flask import current_app, has_app_context


class TwitterURLBuilder:
    """Twitter/X URL构建器"""
    
    @staticmethod
    def get_base_url() -> str:
        """获取基础URL"""
        if has_app_context():
            return current_app.config.get('TWITTER_BASE_URL', 'https://x.com')
        else:
            return os.getenv('TWITTER_BASE_URL', 'https://x.com')
    
    @staticmethod 
    def get_legacy_url() -> str:
        """获取旧版URL"""
        if has_app_context():
            return current_app.config.get('TWITTER_LEGACY_URL', 'https://twitter.com')
        else:
            return os.getenv('TWITTER_LEGACY_URL', 'https://twitter.com')
    
    @staticmethod
    def build_tweet_url(username: str, tweet_id: str, use_legacy: bool = False) -> str:
        """构建推文URL
        
        Args:
            username: 用户名
            tweet_id: 推文ID
            use_legacy: 是否使用旧版URL
            
        Returns:
            完整的推文URL
        """
        if not username or not tweet_id:
            return ""
        
        base_url = TwitterURLBuilder.get_legacy_url() if use_legacy else TwitterURLBuilder.get_base_url()
        return f"{base_url}/{username}/status/{tweet_id}"
    
    @staticmethod
    def build_web_tweet_url(tweet_id: str) -> str:
        """构建Web接口推文URL（用于爬虫）"""
        base_url = TwitterURLBuilder.get_base_url()
        return f"{base_url}/i/web/status/{tweet_id}"
    
    @staticmethod
    def build_profile_url(username: str) -> str:
        """构建用户资料URL"""
        base_url = TwitterURLBuilder.get_base_url()
        return f"{base_url}/{username}"
    
    @staticmethod
    def build_search_url(query: str) -> str:
        """构建搜索URL"""
        base_url = TwitterURLBuilder.get_base_url()
        encoded_query = query.replace(' ', '%20')
        return f"{base_url}/search?q={encoded_query}&src=typed_query"


# 向后兼容的函数
def build_tweet_url(username: str, tweet_id: str, use_legacy: bool = False) -> str:
    """构建推文URL（向后兼容函数）"""
    return TwitterURLBuilder.build_tweet_url(username, tweet_id, use_legacy)


def build_web_tweet_url(tweet_id: str) -> str:
    """构建Web接口推文URL（向后兼容函数）"""
    return TwitterURLBuilder.build_web_tweet_url(tweet_id)