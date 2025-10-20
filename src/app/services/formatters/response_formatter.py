"""
简化版响应格式化器
用于提供更清晰、简洁的API响应
"""

from typing import Dict, Any, Optional
from ..utils.url_builder import TwitterURLBuilder


class TweetResponseFormatter:
    """推文响应格式化器
    
    实现user_tweet + primary_tweet双字段结构，
    使用统一的action_info设计，确保下游服务稳定解析。
    """
    
    def format_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化推文响应数据为统一结构
        
        Args:
            raw_data: 原始提取数据
            
        Returns:
            格式化后的响应数据
        """
        return self._format_response(raw_data)
    
    
    def _format_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """user_tweet + primary_tweet双字段结构"""
        # 获取目标推文ID（URL中指定的推文）
        target_tweet_id = raw_data.get('extraction_metadata', {}).get('target_tweet_id')
        
        # 查找用户推文（URL指定的推文）
        user_tweet_data = self._find_user_tweet(raw_data, target_tweet_id)
        if not user_tweet_data:
            return {
                "user_tweet": None,
                "primary_tweet": None,
                "thread": [],
                "related": [],
                "summary": {
                    "total_tweets": 0,
                    "has_thread": False,
                    "has_replies": False
                }
            }
        
        # 构造真正的用户推文和主推文
        user_tweet, primary_tweet = self._construct_user_and_primary_tweets(user_tweet_data, target_tweet_id)
        
        # 格式化推文
        formatted_user_tweet = self._simplify_tweet(user_tweet)
        formatted_primary_tweet = self._simplify_tweet(primary_tweet) if primary_tweet else None
        
        
        # 格式化线程和相关推文
        thread_tweets = [
            self._simplify_tweet(tweet) 
            for tweet in raw_data.get('thread_tweets', [])
        ]
        
        related_tweets = [
            self._simplify_tweet(tweet) 
            for tweet in raw_data.get('related_tweets', [])
        ]
        
        return {
            "user_tweet": formatted_user_tweet,
            "primary_tweet": formatted_primary_tweet,
            "thread": thread_tweets,
            "related": related_tweets,
            "summary": {
                "total_tweets": len([t for t in [formatted_user_tweet, formatted_primary_tweet] if t]) + len(thread_tweets) + len(related_tweets),
                "has_thread": len(thread_tweets) > 0,
                "has_replies": len(related_tweets) > 0
            }
        }
    
    def _simplify_tweet(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """简化单个推文数据
        
        直接返回推文的原始内容，保持数据原始性。
        添加必要的交互信息（引用、回复、转发）。
        """
        if not tweet:
            return None
        
        tweet_type = tweet.get('tweet_type', 'normal')
        
        simplified = {
            "id": tweet.get('tweet_id'),
            "text": tweet.get('text', ''),
            "author": self._simplify_author(tweet.get('author', {})),
            "time": tweet.get('timestamp'),
            "metrics": self._simplify_metrics(tweet.get('metrics', {})),
            "type": self._normalize_tweet_type(tweet_type)
        }
        
        # 保留内部标记字段用于数据增强
        if tweet.get('_enhance_with_real_data'):
            simplified['_enhance_with_real_data'] = True
        if tweet.get('_real_tweet_url'):
            simplified['_real_tweet_url'] = tweet.get('_real_tweet_url')
        
        # 添加交互信息
        self._add_interaction_info(simplified, tweet, tweet_type)
        
        return simplified
    
    def _normalize_tweet_type(self, tweet_type: str) -> str:
        """标准化推文类型"""
        type_mapping = {
            'quote': 'quote',
            'retweet': 'retweet', 
            'reply': 'reply',
            'normal': 'original'
        }
        return type_mapping.get(tweet_type, 'original')
    
    def _add_interaction_info(self, simplified: Dict[str, Any], tweet: Dict[str, Any], tweet_type: str):
        """添加统一的动作信息（action_info）"""
        if tweet_type == 'quote' and tweet.get('quoted_tweet'):
            quoted = tweet.get('quoted_tweet', {})
            simplified['action_info'] = {
                "target": {
                    "author": quoted.get('author', {}).get('username'),
                    "text": quoted.get('text', ''),
                    "url": self._generate_tweet_url(quoted.get('author', {}).get('username'), quoted.get('tweet_id')),
                    "id": quoted.get('tweet_id')
                }
            }
        
        elif tweet_type == 'retweet' and tweet.get('retweeted_tweet'):
            retweeted = tweet.get('retweeted_tweet', {})
            simplified['action_info'] = {
                "target": {
                    "author": retweeted.get('original_author', {}).get('username'),
                    "text": tweet.get('text', ''),  # 被转发的内容
                    "id": retweeted.get('original_tweet_id')
                }
            }
        
        elif tweet_type == 'reply' and tweet.get('reply_context'):
            reply_ctx = tweet.get('reply_context', {})
            # 清理回复用户名（移除@符号）
            replying_to_users = reply_ctx.get('replying_to_users', [])
            target_author = None
            if replying_to_users:
                target_author = replying_to_users[0].replace('@', '') if replying_to_users[0] else None
            
            simplified['action_info'] = {
                "target": {
                    "author": target_author,
                    "text": reply_ctx.get('replying_to_text', ''),
                    "id": reply_ctx.get('original_tweet_id')
                }
            }
    
    def _find_user_tweet(self, raw_data: Dict[str, Any], target_tweet_id: str) -> Optional[Dict[str, Any]]:
        """查找用户推文（URL指定的推文）"""
        if not target_tweet_id:
            # 如果没有目标ID，返回主推文
            return raw_data.get('primary_tweet')
        
        # 在所有推文中查找目标推文
        all_tweets = []
        
        # 添加主推文
        if raw_data.get('primary_tweet'):
            all_tweets.append(raw_data['primary_tweet'])
        
        # 添加线程推文
        all_tweets.extend(raw_data.get('thread_tweets', []))
        
        # 添加相关推文
        all_tweets.extend(raw_data.get('related_tweets', []))
        
        # 查找匹配的推文
        for tweet in all_tweets:
            if tweet and tweet.get('tweet_id') == target_tweet_id:
                return tweet
        
        # 如果找不到，返回主推文作为默认
        return raw_data.get('primary_tweet')
    
    
    def _find_tweet_by_id(self, raw_data: Dict[str, Any], tweet_id: str) -> Optional[Dict[str, Any]]:
        """在数据中查找指定 ID 的推文"""
        all_tweets = []
        
        if raw_data.get('primary_tweet'):
            all_tweets.append(raw_data['primary_tweet'])
        
        all_tweets.extend(raw_data.get('thread_tweets', []))
        all_tweets.extend(raw_data.get('related_tweets', []))
        
        for tweet in all_tweets:
            if tweet and tweet.get('tweet_id') == tweet_id:
                return tweet
        
        return None
    
    def _construct_user_and_primary_tweets(self, tweet_data: Dict[str, Any], target_tweet_id: str = None) -> tuple:
        """构造用户推文和主推文
        
        根据原始数据构造正确的用户推文和主推文。
        解决重复内容问题。
        """
        if not tweet_data:
            return None, None
        
        # 使用tweet_type字段识别推文类型（不依赖action信息）
        tweet_type = tweet_data.get('tweet_type', 'normal')
        
        
        if tweet_type == 'quote' and tweet_data.get('quoted_tweet'):
            # 引用推文情况
            quoted_tweet = tweet_data.get('quoted_tweet', {})
            
            # 检查是否是自引用（用户引用自己的推文）
            is_self_quote = quoted_tweet.get('tweet_id') == tweet_data.get('tweet_id')
            
            # user_tweet: 用户的引用动作  
            # 对于自引用，强制添加_quote后缀以避免ID重复
            user_tweet_id = target_tweet_id or tweet_data.get('tweet_id')
            if is_self_quote and user_tweet_id:
                user_tweet_id = f"{user_tweet_id}_quote"
            
            user_tweet = {
                'tweet_id': user_tweet_id,
                'text': tweet_data.get('text', ''),  # 引用评论
                'author': tweet_data.get('author', {}),   # 引用者
                'timestamp': tweet_data.get('timestamp'),
                'metrics': tweet_data.get('metrics', {}),
                'tweet_type': 'quote',
                'quoted_tweet': quoted_tweet
            }
            
            # primary_tweet: 被引用的原推文
            primary_tweet = {
                'tweet_id': quoted_tweet.get('tweet_id'),
                'text': quoted_tweet.get('text'),
                'author': quoted_tweet.get('author', {}),
                'timestamp': quoted_tweet.get('timestamp'),
                'metrics': quoted_tweet.get('metrics', {}),  # 保留原有metrics，等待增强
                'tweet_type': 'normal',
                # 标记需要获取真实数据
                '_enhance_with_real_data': True,
                '_real_tweet_url': self._generate_tweet_url(
                    quoted_tweet.get('author', {}).get('username'),
                    quoted_tweet.get('tweet_id')
                )
            }
        
        elif tweet_type == 'retweet' and tweet_data.get('retweeted_tweet'):
            # 转发推文情况
            retweeted_data = tweet_data.get('retweeted_tweet', {})
            
            user_tweet = {
                'tweet_id': target_tweet_id or tweet_data.get('tweet_id'),
                'text': retweeted_data.get('retweet_comment', ''),
                'author': tweet_data.get('author', {}),
                'timestamp': tweet_data.get('timestamp'),
                'metrics': tweet_data.get('metrics', {}),
                'tweet_type': 'retweet',
                'retweeted_tweet': retweeted_data
            }
            
            primary_tweet = {
                'tweet_id': retweeted_data.get('original_tweet_id'),
                'text': tweet_data.get('text'),  # 被转发的内容
                'author': retweeted_data.get('original_author', {}),
                'timestamp': tweet_data.get('timestamp'),
                'metrics': tweet_data.get('metrics', {}),
                'tweet_type': 'normal'
            }
        
        elif tweet_type == 'reply' and tweet_data.get('reply_context'):
            # 回复推文情况
            reply_ctx = tweet_data.get('reply_context', {})
            
            user_tweet = {
                'tweet_id': target_tweet_id or tweet_data.get('tweet_id'),
                'text': tweet_data.get('text'),
                'author': tweet_data.get('author', {}),
                'timestamp': tweet_data.get('timestamp'),
                'metrics': tweet_data.get('metrics', {}),
                'tweet_type': 'reply',
                'reply_context': reply_ctx
            }
            
            # 查找被回复的原推文
            original_tweet_id = reply_ctx.get('original_tweet_id')
            if original_tweet_id:
                primary_tweet = {
                    'tweet_id': original_tweet_id,
                    'text': reply_ctx.get('replying_to_text', ''),
                    'author': {'username': reply_ctx.get('replying_to_users', [''])[0].replace('@', '')},
                    'timestamp': None,
                    'metrics': {},
                    'tweet_type': 'normal'
                }
            else:
                primary_tweet = None
        
        else:
            # 原创推文情况
            user_tweet = tweet_data
            primary_tweet = None  # 原创推文没有主推文
        
        return user_tweet, primary_tweet
    
    
    def _generate_tweet_url(self, username: str, tweet_id: str) -> str:
        """生成推文链接"""
        return TwitterURLBuilder.build_tweet_url(username, tweet_id)
    
    
    def _simplify_author(self, author: Dict[str, Any]) -> Dict[str, Any]:
        """简化作者信息 - 确保所有必要字段"""
        if not author:
            return {
                "username": None,
                "name": None,
                "avatar": None,
                "verified": False
            }
        
        return {
            "username": author.get('username'),
            "name": author.get('display_name') or author.get('name'),
            "avatar": author.get('avatar_url'),
            "verified": author.get('is_verified', False)
        }
    
    def _simplify_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """简化指标数据 - 确保所有互动数据完整"""
        if not metrics:
            return {
                "likes": 0,
                "retweets": 0,
                "replies": 0,
                "quotes": 0,
                "views": 0
            }
        
        # 如果metrics是字典且不为空，保留原始数据结构供后续增强使用
        return {
            "likes": int(metrics.get('likes', 0)),
            "retweets": int(metrics.get('retweets', 0)),
            "replies": int(metrics.get('replies', 0)),
            "quotes": int(metrics.get('quotes', 0)),
            "views": int(metrics.get('views', 0))
        }


class ResponseFormatterFactory:
    """响应格式化器工厂类"""
    
    @staticmethod
    def create_formatter() -> TweetResponseFormatter:
        """创建推文响应格式化器"""
        return TweetResponseFormatter()