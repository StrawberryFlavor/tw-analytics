"""
Apify 数据源实现
提供基于 Apify Actors 的 Twitter 数据获取服务
"""

import asyncio
import logging
import time
import os
from typing import Dict, Any, Optional, List
import httpx
from urllib.parse import urlparse, parse_qs

from ...core.interfaces import DataSourceInterface, TweetData, UserData
from ...core.exceptions import DataSourceError, DataSourceUnavailableError


def convert_proxy_for_httpx(proxy_url: str) -> Optional[str]:
    """
    转换代理URL为httpx兼容格式
    
    Args:
        proxy_url: 原始代理URL，支持 http://, https://, socks5://, socks5h://
        
    Returns:
        httpx兼容的代理URL，如果不支持则返回None
    """
    if not proxy_url:
        return None
    
    try:
        parsed = urlparse(proxy_url)
        scheme = parsed.scheme.lower()
        
        # httpx支持的代理协议
        if scheme in ['http', 'https']:
            return proxy_url
        elif scheme in ['socks5', 'socks5h']:
            # 将socks5h://转换为socks5://（httpx不支持socks5h）
            return f"socks5://{parsed.netloc}"
        else:
            # 不支持的协议
            return None
    except Exception:
        return None


class ApifyDataTransformer:
    """Apify数据转换器，将Apify格式转换为系统标准格式"""
    
    @staticmethod
    def transform_to_standard_format(apify_data: Any) -> Dict[str, Any]:
        """
        将Apify返回的数据转换为系统标准格式
        
        Args:
            apify_data: Apify原始数据（可能是list或dict）
            
        Returns:
            标准化的推文数据
        """
        if not apify_data:
            return {}
        
        # 处理不同的数据格式
        if isinstance(apify_data, list):
            # 如果是列表，取第一个元素
            if len(apify_data) == 0:
                return {}
            tweet_data = apify_data[0]
        elif isinstance(apify_data, dict):
            # 如果是字典，直接使用
            tweet_data = apify_data
        elif isinstance(apify_data, str):
            # 如果是字符串，尝试解析JSON
            try:
                import json
                tweet_data = json.loads(apify_data)
            except:
                return {}
        else:
            return {}
        
        # 提取主要推文数据
        if isinstance(tweet_data, dict):
            tweet = tweet_data
        else:
            return {}
        
        # 构建标准格式数据
        standard_data = {
            'primary_tweet': ApifyDataTransformer._transform_single_tweet(tweet),
            'thread_tweets': [],
            'related_tweets': [],
            'extraction_metadata': {
                'timestamp': int(time.time()),
                'source': 'apify',
                'total_tweets_found': 1 if isinstance(tweet_data, dict) else len(apify_data) if isinstance(apify_data, list) else 0
            }
        }
        
        return standard_data
    
    @staticmethod
    def _transform_single_tweet(tweet: Dict[str, Any]) -> Dict[str, Any]:
        """转换单个推文数据 - 基于真实的Apify格式"""
        if not tweet:
            return {}
        
        return {
            'tweet_id': tweet.get('id', ''),
            'text': tweet.get('description', ''),
            'author': {
                'id': tweet.get('user_posted', ''),
                'username': tweet.get('user_posted', ''),
                'name': tweet.get('name', ''),
                'description': tweet.get('biography', ''),
                'followers_count': tweet.get('followers', 0),
                'following_count': tweet.get('following', 0),
                'tweet_count': tweet.get('posts_count', 0),
                'verified': tweet.get('is_verified', False),
                'profile_image_url': tweet.get('profile_image_link', ''),
                'created_at': None
            },
            'timestamp': tweet.get('date_posted', ''),
            'metrics': {
                'views': tweet.get('views', 0),
                'likes': tweet.get('likes', 0),
                'retweets': tweet.get('reposts', 0),
                'replies': tweet.get('replies', 0),
                'quotes': tweet.get('quotes', 0)
            },
            'media': ApifyDataTransformer._extract_apify_media(tweet),
            'links': [tweet.get('external_url')] if tweet.get('external_url') else [],
            'hashtags': tweet.get('hashtags') or [],
            'mentions': [user.get('profile_name', '') for user in (tweet.get('tagged_users') or [])],
            'tweet_type': ApifyDataTransformer._determine_apify_tweet_type(tweet),
            'language': None,
            'location': None,
            'quoted_tweet': ApifyDataTransformer._extract_apify_quoted_tweet(tweet),
            'reply_context': None,
            'retweeted_tweet': None
        }
    
    @staticmethod
    def _extract_author(tweet: Dict[str, Any]) -> Dict[str, Any]:
        """提取作者信息"""
        author = tweet.get('author', {}) or tweet.get('user', {})
        
        return {
            'id': author.get('id') or author.get('id_str'),
            'username': author.get('username') or author.get('screen_name'),
            'name': author.get('name'),
            'description': author.get('description'),
            'followers_count': author.get('followers_count', 0),
            'following_count': author.get('friends_count', 0),
            'tweet_count': author.get('statuses_count', 0),
            'verified': author.get('verified', False),
            'profile_image_url': author.get('profile_image_url'),
            'created_at': author.get('created_at')
        }
    
    @staticmethod
    def _extract_timestamp(tweet: Dict[str, Any]) -> Optional[str]:
        """提取时间戳"""
        return tweet.get('created_at') or tweet.get('createdAt')
    
    @staticmethod
    def _extract_metrics(tweet: Dict[str, Any]) -> Dict[str, int]:
        """提取互动指标"""
        return {
            'views': tweet.get('views', 0) or tweet.get('viewCount', 0),
            'likes': tweet.get('likes', 0) or tweet.get('favorite_count', 0),
            'retweets': tweet.get('retweets', 0) or tweet.get('retweet_count', 0),
            'replies': tweet.get('replies', 0) or tweet.get('reply_count', 0),
            'quotes': tweet.get('quotes', 0) or tweet.get('quote_count', 0)
        }
    
    @staticmethod
    def _extract_media(tweet: Dict[str, Any]) -> List[Dict[str, Any]]:
        """提取媒体内容"""
        media_list = []
        
        # 处理图片
        if 'photos' in tweet:
            for photo in tweet.get('photos', []):
                media_list.append({
                    'type': 'photo',
                    'url': photo.get('url'),
                    'alt_text': photo.get('alt_text')
                })
        
        # 处理视频
        if 'videos' in tweet:
            for video in tweet.get('videos', []):
                media_list.append({
                    'type': 'video',
                    'url': video.get('url'),
                    'thumbnail': video.get('thumbnail'),
                    'duration': video.get('duration')
                })
        
        return media_list
    
    @staticmethod
    def _extract_links(tweet: Dict[str, Any]) -> List[str]:
        """提取链接"""
        links = tweet.get('urls', [])
        return [link.get('expanded_url') or link.get('url') for link in links if link]
    
    @staticmethod
    def _extract_hashtags(tweet: Dict[str, Any]) -> List[str]:
        """提取话题标签"""
        hashtags = tweet.get('hashtags', [])
        return [tag.get('text') or tag for tag in hashtags if tag]
    
    @staticmethod
    def _extract_mentions(tweet: Dict[str, Any]) -> List[str]:
        """提取用户提及"""
        mentions = tweet.get('mentions', [])
        return [mention.get('username') or mention.get('screen_name') or mention 
                for mention in mentions if mention]
    
    @staticmethod
    def _determine_tweet_type(tweet: Dict[str, Any]) -> str:
        """确定推文类型"""
        if tweet.get('quoted_status') or tweet.get('quotedTweet'):
            return 'quote'
        elif tweet.get('retweeted_status') or tweet.get('isRetweet'):
            return 'retweet'
        elif tweet.get('in_reply_to_status_id') or tweet.get('isReply'):
            return 'reply'
        else:
            return 'normal'
    
    @staticmethod
    def _extract_quoted_tweet(tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取引用推文"""
        quoted = tweet.get('quoted_status') or tweet.get('quotedTweet')
        if quoted:
            return ApifyDataTransformer._transform_single_tweet(quoted)
        return None
    
    @staticmethod
    def _extract_reply_context(tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取回复上下文"""
        if tweet.get('in_reply_to_status_id'):
            return {
                'replying_to_id': tweet.get('in_reply_to_status_id'),
                'replying_to_users': [tweet.get('in_reply_to_screen_name')] if tweet.get('in_reply_to_screen_name') else [],
                'original_tweet_id': tweet.get('in_reply_to_status_id')
            }
        return None
    
    @staticmethod
    def _extract_retweet_context(tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取转发上下文"""
        retweeted = tweet.get('retweeted_status')
        if retweeted:
            return {
                'original_tweet_id': retweeted.get('id'),
                'original_author': ApifyDataTransformer._extract_author(retweeted)
            }
        return None
    
    @staticmethod
    def _extract_apify_media(tweet: Dict[str, Any]) -> List[Dict[str, Any]]:
        """提取Apify格式的媒体内容"""
        media_list = []
        
        # 处理图片
        if tweet.get('photos'):
            for photo_url in tweet.get('photos', []):
                media_list.append({
                    'type': 'photo',
                    'url': photo_url,
                    'alt_text': None
                })
        
        # 处理视频
        if tweet.get('videos'):
            for video_url in tweet.get('videos', []):
                media_list.append({
                    'type': 'video',
                    'url': video_url,
                    'thumbnail': None,
                    'duration': None
                })
        
        return media_list
    
    @staticmethod
    def _determine_apify_tweet_type(tweet: Dict[str, Any]) -> str:
        """确定Apify格式的推文类型"""
        quoted_post = tweet.get('quoted_post', {})
        if quoted_post and quoted_post.get('post_id'):
            return 'quote'
        elif tweet.get('reposts', 0) > 0:
            return 'retweet'  # 这个可能不准确，需要更多字段判断
        else:
            return 'normal'
    
    @staticmethod
    def _extract_apify_quoted_tweet(tweet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取Apify格式的引用推文"""
        quoted_post = tweet.get('quoted_post', {})
        if quoted_post and quoted_post.get('post_id'):
            return {
                'tweet_id': quoted_post.get('post_id'),
                'text': quoted_post.get('description', ''),
                'author': {
                    'id': quoted_post.get('profile_id', ''),
                    'username': quoted_post.get('profile_name', ''),
                    'name': quoted_post.get('profile_name', '')
                },
                'timestamp': quoted_post.get('data_posted'),
                'media': []
            }
        return None


class ApifyTwitterSource(DataSourceInterface):
    """Apify Twitter数据源实现"""
    
    def __init__(self, api_token: str, actor_id: str = "apidojo/tweet-scraper", timeout: int = 120):
        """
        初始化Apify数据源
        
        Args:
            api_token: Apify API令牌
            actor_id: 要使用的Actor ID
            timeout: 请求超时时间（秒）
        """
        self.api_token = api_token
        self.actor_id = actor_id
        self.timeout = timeout
        self.base_url = "https://api.apify.com/v2"
        
        # 配置代理
        self.proxy = self._configure_proxy()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"ApifyTwitterSource initialized with actor: {actor_id}")
        if self.proxy:
            self.logger.info(f"Using proxy: {self.proxy}")
    
    def _configure_proxy(self) -> Optional[str]:
        """
        配置代理设置，从环境变量读取并转换为httpx兼容格式
        
        Returns:
            httpx兼容的代理URL，如果没有配置或不支持则返回None
        """
        # 尝试从环境变量获取代理配置
        proxy_sources = [
            os.getenv('PLAYWRIGHT_PROXY'),  # 复用Playwright的代理配置
            os.getenv('HTTP_PROXY'),        # 标准HTTP代理环境变量
            os.getenv('HTTPS_PROXY'),       # 标准HTTPS代理环境变量
        ]
        
        for proxy_url in proxy_sources:
            if proxy_url:
                converted_proxy = convert_proxy_for_httpx(proxy_url)
                if converted_proxy:
                    return converted_proxy
                else:
                    self.logger.warning(f"不支持的代理协议: {proxy_url}")
        
        return None
    
    @property
    def name(self) -> str:
        """数据源名称"""
        return "apify"
    
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return bool(self.api_token and self.actor_id)
    
    async def get_tweet_data(self, tweet_id: str) -> TweetData:
        """
        获取推文数据（简化接口）
        
        Args:
            tweet_id: 推文ID
            
        Returns:
            推文数据对象
        """
        # 构建推文URL
        tweet_url = f"https://twitter.com/i/status/{tweet_id}"
        
        # 获取综合数据
        comprehensive_data = await self.get_comprehensive_data(tweet_url)
        
        if not comprehensive_data:
            raise DataSourceError(f"Failed to get tweet data for ID: {tweet_id}")
        
        # 提取主推文
        primary_tweet = comprehensive_data.get('primary_tweet', {})
        
        # 转换为TweetData对象
        return TweetData(
            tweet_id=primary_tweet.get('tweet_id', tweet_id),
            text=primary_tweet.get('text', ''),
            author_id=primary_tweet.get('author', {}).get('id', ''),
            author_username=primary_tweet.get('author', {}).get('username', ''),
            created_at=primary_tweet.get('timestamp', ''),
            public_metrics=primary_tweet.get('metrics', {})
        )
    
    async def get_user_data(self, username: str) -> UserData:
        """
        获取用户数据（暂不实现）
        
        Args:
            username: 用户名
            
        Returns:
            用户数据对象
        """
        raise NotImplementedError("User data retrieval not implemented for Apify source")
    
    async def get_comprehensive_data(self, tweet_url: str) -> Optional[Dict[str, Any]]:
        """
        获取综合推文数据
        
        Args:
            tweet_url: 推文URL
            
        Returns:
            综合推文数据
        """
        try:
            self.logger.info(f"Getting comprehensive data for URL: {tweet_url}")
            
            # 准备输入数据
            input_data = self._prepare_input_data(tweet_url)
            
            # 运行Actor
            run_id = await self._run_actor(input_data)
            if not run_id:
                return None
            
            # 等待完成并获取结果
            if await self._wait_for_completion(run_id):
                results = await self._get_results(run_id)
                if results:
                    # 转换为标准格式
                    return ApifyDataTransformer.transform_to_standard_format(results)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get comprehensive data: {e}")
            raise DataSourceError(f"Apify data retrieval failed: {str(e)}")
    
    def _prepare_input_data(self, tweet_url: str) -> Dict[str, Any]:
        """准备Actor输入数据"""
        return {
            "url": tweet_url  # 单个URL格式，匹配 ow5loPc1VwudoP5vY Actor 的要求
        }
    
    async def _run_actor(self, input_data: Dict[str, Any]) -> Optional[str]:
        """
        运行Apify Actor
        
        Args:
            input_data: 输入数据
            
        Returns:
            运行ID
        """
        try:
            url = f"{self.base_url}/acts/{self.actor_id}/runs"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            # 创建客户端配置
            client_kwargs = {"timeout": 30}
            if self.proxy:
                # httpx新版本代理格式
                client_kwargs["proxy"] = self.proxy
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(url, json=input_data, headers=headers)
                
                if response.status_code == 201:
                    result = response.json()
                    run_id = result.get("data", {}).get("id")
                    self.logger.info(f"Actor run started with ID: {run_id}")
                    return run_id
                else:
                    self.logger.error(f"Failed to start actor run: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error starting actor run: {e}")
            return None
    
    async def _wait_for_completion(self, run_id: str) -> bool:
        """
        等待Actor运行完成
        
        Args:
            run_id: 运行ID
            
        Returns:
            是否成功完成
        """
        try:
            url = f"{self.base_url}/acts/{self.actor_id}/runs/{run_id}"
            headers = {"Authorization": f"Bearer {self.api_token}"}
            
            start_time = time.time()
            
            while time.time() - start_time < self.timeout:
                # 创建客户端配置
                client_kwargs = {"timeout": 10}
                if self.proxy:
                    # httpx新版本代理格式
                    client_kwargs["proxy"] = self.proxy
                
                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        result = response.json()
                        status = result.get("data", {}).get("status")
                        
                        if status == "SUCCEEDED":
                            self.logger.info(f"Actor run {run_id} completed successfully")
                            return True
                        elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                            self.logger.error(f"Actor run {run_id} failed with status: {status}")
                            return False
                        
                        # 状态为 READY, RUNNING - 继续等待
                        await asyncio.sleep(5)  # 等待5秒后重试
                    else:
                        self.logger.error(f"Error checking run status: {response.status_code}")
                        return False
            
            self.logger.error(f"Actor run {run_id} timed out after {self.timeout} seconds")
            return False
            
        except Exception as e:
            self.logger.error(f"Error waiting for completion: {e}")
            return False
    
    async def _get_results(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        获取Actor运行结果
        
        Args:
            run_id: 运行ID
            
        Returns:
            结果数据
        """
        try:
            # 首先获取运行信息以获得defaultDatasetId
            run_url = f"{self.base_url}/acts/{self.actor_id}/runs/{run_id}"
            headers = {"Authorization": f"Bearer {self.api_token}"}
            
            # 创建客户端配置
            client_kwargs = {"timeout": 30}
            if self.proxy:
                # httpx新版本代理格式
                client_kwargs["proxy"] = self.proxy
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                # 获取运行信息
                run_response = await client.get(run_url, headers=headers)
                
                if run_response.status_code != 200:
                    self.logger.error(f"Error getting run info: {run_response.status_code} - {run_response.text}")
                    return None
                
                run_data = run_response.json()
                dataset_id = run_data.get("data", {}).get("defaultDatasetId")
                
                if not dataset_id:
                    self.logger.warning("No defaultDatasetId found in run data")
                    return None
                
                # 使用正确的数据集API获取结果
                dataset_url = f"{self.base_url}/datasets/{dataset_id}/items"
                self.logger.info(f"Fetching results from dataset: {dataset_id}")
                
                response = await client.get(dataset_url, headers=headers)
                
                if response.status_code == 200:
                    items = response.json()
                    if items:
                        self.logger.info(f"Retrieved {len(items)} result items from Apify")
                        # 返回原始数据，让转换器处理
                        return items
                    else:
                        self.logger.warning("No results found in dataset")
                        return None
                else:
                    self.logger.error(f"Error getting results: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting results: {e}")
            return None