"""
Python客户端接口 - 用于程序化调用
"""

import os
from typing import List, Dict, Any

from ..app.core.container import get_app_container
from ..app.services.utils import clean_username
from ..app.core.path_manager import load_env_file

# 加载环境变量
load_env_file()


class TwitterClient:
    """Twitter数据分析客户端"""
    
    def __init__(self, bearer_token: str = None):
        """初始化客户端
        
        Args:
            bearer_token: Twitter Bearer Token，如果不提供则从环境变量读取
        """
        if bearer_token:
            os.environ['TWITTER_BEARER_TOKEN'] = bearer_token
        
        # 验证配置
        if not os.getenv('TWITTER_BEARER_TOKEN'):
            raise ValueError("TWITTER_BEARER_TOKEN未设置")
        
        # 创建模拟的Flask应用上下文和服务容器
        self._setup_mock_app_context()
        self.container = get_app_container()
        self.service = self.container.get('twitter_service')
    
    def _setup_mock_app_context(self):
        """设置模拟的Flask应用上下文"""
        import flask
        
        # 创建临时应用
        app = flask.Flask(__name__)
        app.config.update({
            'TWITTER_BEARER_TOKEN': os.getenv('TWITTER_BEARER_TOKEN'),
            'MAX_TWEETS_PER_REQUEST': int(os.getenv('MAX_TWEETS_PER_REQUEST', '100')),
            'MAX_BATCH_SIZE': int(os.getenv('MAX_BATCH_SIZE', '50')),
            'DEFAULT_TWEET_COUNT': int(os.getenv('DEFAULT_TWEET_COUNT', '10'))
        })
        
        # 推送应用上下文
        self.app_context = app.app_context()
        self.app_context.push()
    
    @classmethod
    def from_env(cls) -> 'TwitterClient':
        """从环境变量创建客户端"""
        return cls()
    
    def get_tweet_views(self, tweet_id: str) -> int:
        """获取推特浏览量"""
        tweet_id = self._extract_tweet_id(tweet_id)
        return self.service.get_tweet_views_sync(tweet_id)
    
    def get_tweet_info(self, tweet_id: str) -> Dict[str, Any]:
        """获取推特完整信息"""
        tweet_id = self._extract_tweet_id(tweet_id)
        tweet_data = self.service.get_tweet_metrics_sync(tweet_id)
        return {
            "tweet_id": tweet_data.tweet_id,
            "text": tweet_data.text,
            "author_username": tweet_data.author_username,
            "author_name": tweet_data.author_name,
            "created_at": tweet_data.created_at,
            "public_metrics": tweet_data.public_metrics,
            "view_count": tweet_data.view_count,
            "url": tweet_data.url,
            "lang": tweet_data.lang,
            "engagement_rate": tweet_data.engagement_rate
        }
    
    def get_tweet_by_url(self, tweet_url: str) -> Dict[str, Any]:
        """通过URL获取推特完整信息"""
        tweet_data = self.service.get_tweet_by_url_sync(tweet_url)
        return {
            "tweet_id": tweet_data.tweet_id,
            "text": tweet_data.text,
            "author_username": tweet_data.author_username,
            "author_name": tweet_data.author_name,
            "created_at": tweet_data.created_at,
            "public_metrics": tweet_data.public_metrics,
            "view_count": tweet_data.view_count,
            "url": tweet_data.url,
            "lang": tweet_data.lang,
            "engagement_rate": tweet_data.engagement_rate
        }
    
    def batch_get_tweets_by_urls(self, tweet_urls: List[str]) -> List[Dict[str, Any]]:
        """批量通过URL获取推特信息"""
        tweets_data = self.service.batch_get_tweets_by_urls_sync(tweet_urls)
        return [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in tweets_data
        ]
    
    def get_user_info(self, username: str) -> Dict[str, Any]:
        """获取用户信息"""
        username = clean_username(username)
        user_data = self.service.get_user_info_sync(username)
        return {
            "user_id": user_data.user_id,
            "username": user_data.username,
            "name": user_data.name,
            "description": user_data.description,
            "public_metrics": user_data.public_metrics,
            "profile_image_url": user_data.profile_image_url,
            "verified": user_data.verified,
            "created_at": user_data.created_at
        }
    
    def get_user_recent_tweets(self, username: str, count: int = 5) -> List[Dict[str, Any]]:
        """获取用户最近推特"""
        username = clean_username(username)
        tweets_data = self.service.get_user_recent_tweets_with_metrics_sync(username, count)
        return [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in tweets_data
        ]
    
    def search_tweets(self, keyword: str, count: int = 10) -> List[Dict[str, Any]]:
        """搜索推特"""
        search_results = self.service.search_tweets_sync(keyword, count)
        return [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in search_results
        ]
    
    def get_engagement_rate(self, tweet_id: str) -> Dict[str, Any]:
        """获取推特互动率"""
        tweet_id = self._extract_tweet_id(tweet_id)
        engagement_rate = self.service.get_tweet_engagement_rate_sync(tweet_id)
        return {
            "tweet_id": tweet_id,
            "engagement_rate": engagement_rate
        }
    
    def batch_get_views(self, tweet_ids: List[str]) -> Dict[str, int]:
        """批量获取推特浏览量"""
        clean_ids = [self._extract_tweet_id(tweet_id) for tweet_id in tweet_ids]
        return self.service.batch_get_tweet_views_sync(clean_ids)
    
    def _extract_tweet_id(self, tweet_input: str) -> str:
        """从URL或输入中提取推特ID"""
        if 'twitter.com' in tweet_input or 'x.com' in tweet_input:
            parts = tweet_input.rstrip('/').split('/')
            if 'status' in parts:
                status_index = parts.index('status')
                if status_index + 1 < len(parts):
                    tweet_id = parts[status_index + 1]
                    return tweet_id.split('?')[0]
            raise ValueError(f"无法从URL提取推特ID: {tweet_input}")
        
        return tweet_input.split('?')[0]
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'app_context'):
            self.app_context.pop()


# 便捷函数
def get_tweet_views(tweet_id: str, bearer_token: str = None) -> int:
    """快速获取推特浏览量"""
    client = TwitterClient(bearer_token) if bearer_token else TwitterClient.from_env()
    return client.get_tweet_views(tweet_id)


def get_user_info(username: str, bearer_token: str = None) -> Dict[str, Any]:
    """快速获取用户信息"""
    client = TwitterClient(bearer_token) if bearer_token else TwitterClient.from_env()
    return client.get_user_info(username)


def get_tweet_by_url(tweet_url: str, bearer_token: str = None) -> Dict[str, Any]:
    """快速通过URL获取推特信息"""
    client = TwitterClient(bearer_token) if bearer_token else TwitterClient.from_env()
    return client.get_tweet_by_url(tweet_url)


def batch_get_tweets_by_urls(tweet_urls: List[str], bearer_token: str = None) -> List[Dict[str, Any]]:
    """快速批量通过URL获取推特信息"""
    client = TwitterClient(bearer_token) if bearer_token else TwitterClient.from_env()
    return client.batch_get_tweets_by_urls(tweet_urls)