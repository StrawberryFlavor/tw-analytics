"""
响应数据格式化器
用于将原始提取数据转换为不同格式的API响应
"""

from typing import Dict, Any, List, Optional


class TweetResponseFormatter:
    """推文响应数据格式化器"""
    
    def __init__(self):
        pass
    
    def format_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化为优化的响应数据
        
        Args:
            raw_data: 原始提取数据
            
        Returns:
            优化格式的响应数据
        """
        primary_tweet = raw_data.get('primary_tweet')
        target_tweet_id = raw_data.get('extraction_metadata', {}).get('target_tweet_id')
        
        # Find if target tweet is different from primary
        target_tweet_info = None
        if target_tweet_id and primary_tweet and primary_tweet.get('tweet_id') != target_tweet_id:
            # Look for target tweet in thread
            for tweet in raw_data.get('thread_tweets', []):
                if tweet.get('tweet_id') == target_tweet_id:
                    target_tweet_info = {
                        'id': tweet.get('tweet_id'),
                        'type': tweet.get('semantic_type', 'unknown'),
                        'text': tweet.get('text', ''),
                        'author': tweet.get('author', {}).get('username', ''),
                        'is_target': True
                    }
                    break
        
        response = {
            'tweet': self._clean_tweet_with_type(primary_tweet),
            'thread': [self._clean_tweet_with_type(t) for t in raw_data.get('thread_tweets', [])],
            'related': [self._clean_tweet_with_type(t) for t in raw_data.get('related_tweets', [])],
            'context': self._extract_page_context(raw_data.get('page_context', {})),
            'meta': self._extract_metadata(raw_data.get('extraction_metadata', {}))
        }
        
        # Add target tweet info if different from primary
        if target_tweet_info:
            response['meta']['target_tweet'] = target_tweet_info
            response['meta']['note'] = 'Primary tweet was auto-selected for better content quality'
        
        return response
    
    def _clean_tweet_with_type(self, tweet: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """清理单个推文数据，包含类型信息"""
        if not tweet:
            return None
        
        cleaned = self._clean_tweet(tweet)
        if cleaned:
            # Add semantic type information
            cleaned['type'] = tweet.get('semantic_type', 'unknown')
            
            # Add quality indicators
            metrics = cleaned.get('metrics', {})
            cleaned['quality_score'] = self._calculate_content_quality(tweet, metrics)
        
        return cleaned
    
    def _calculate_content_quality(self, tweet: Dict, metrics: Dict) -> str:
        """Calculate content quality indicator"""
        score = 0
        
        # Text length
        text_len = len(tweet.get('text', ''))
        if text_len > 100: score += 3
        elif text_len > 50: score += 2
        elif text_len > 20: score += 1
        
        # Has media
        if tweet.get('media') and len(tweet.get('media', [])) > 0:
            score += 2
        
        # Engagement (只计算实际可见的指标)
        total_engagement = metrics.get('likes', 0) + metrics.get('retweets', 0) + metrics.get('replies', 0)
        if total_engagement > 100: score += 3
        elif total_engagement > 10: score += 2
        elif total_engagement > 0: score += 1
        
        # Views bonus
        views = metrics.get('views', 0)
        if views > 10000: score += 2
        elif views > 1000: score += 1
        
        if score >= 6: return 'high'
        elif score >= 3: return 'medium'
        else: return 'low'
    
    def _clean_tweet(self, tweet: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        清理单个推文数据
        
        Args:
            tweet: 原始推文数据
            
        Returns:
            清理后的推文数据
        """
        if not tweet:
            return None
            
        # 过滤有用的外部链接
        useful_links = self._filter_useful_links(tweet.get('links', []))
        
        # 过滤无用的mentions（不包含自己）
        useful_mentions = self._filter_useful_mentions(
            tweet.get('mentions', []),
            tweet.get('author', {}).get('username', '')
        )
        
        # 统一主要内容逻辑
        primary_content = self._extract_primary_content(tweet)
        
        # 构建简洁的推文对象
        cleaned_tweet = {
            'id': primary_content['id'],
            'text': primary_content['text'],
            'author': primary_content['author'],
            'time': primary_content['time'],
            'metrics': primary_content['metrics'],
        }
        
        # 添加操作信息（如果是引用、转发等）
        if primary_content.get('action'):
            cleaned_tweet['action'] = primary_content['action']
        
        # 只在有内容时添加可选字段
        self._add_optional_fields(cleaned_tweet, tweet, useful_links, useful_mentions)
        
        return cleaned_tweet
    
    def _extract_primary_content(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取主要内容，统一不同推文类型的数据结构
        
        Args:
            tweet: 原始推文数据
            
        Returns:
            统一格式的主要内容数据
        """
        tweet_type = tweet.get('tweet_type', 'normal')
        
        # 默认主要内容（原创推文、回复推文）
        primary_content = {
            'id': tweet.get('tweet_id'),
            'text': tweet.get('text'),
            'author': self._extract_author_info(tweet.get('author', {})),
            'time': tweet.get('timestamp'),
            'metrics': tweet.get('metrics', {}),
        }
        
        # 根据推文类型调整主要内容
        if tweet_type == 'quote' and tweet.get('quoted_tweet'):
            # 引用推文：主要内容是被引用的推文
            quoted = tweet.get('quoted_tweet')
            primary_content.update({
                'id': quoted.get('tweet_id') or tweet.get('tweet_id'),
                'text': quoted.get('text') or tweet.get('text'),
                'author': self._extract_author_info(quoted.get('author', {})),
                'time': quoted.get('timestamp') or tweet.get('timestamp'),
                'metrics': quoted.get('metrics', {}),
            })
            
            # 同时继承引用推文的链接、媒体等内容
            if quoted.get('links'):
                primary_content['inherited_links'] = quoted.get('links', [])
            if quoted.get('media'):
                primary_content['inherited_media'] = quoted.get('media', [])
            if quoted.get('hashtags'):
                primary_content['inherited_hashtags'] = quoted.get('hashtags', [])
            if quoted.get('mentions'):
                primary_content['inherited_mentions'] = quoted.get('mentions', [])
            
            # 保存引用操作信息
            primary_content['action'] = {
                'type': 'quote',
                'user': self._extract_author_info(tweet.get('author', {})),
                'comment': tweet.get('text'),
                'timestamp': tweet.get('timestamp')
            }
            
        elif tweet_type == 'retweet' and tweet.get('retweeted_tweet'):
            # 转发推文：主要内容是被转发的推文
            retweeted = tweet.get('retweeted_tweet')
            
            # 尝试构建被转发推文的完整信息
            original_author = retweeted.get('original_author', {})
            primary_content.update({
                'id': retweeted.get('original_tweet_id') or tweet.get('tweet_id'),
                'text': tweet.get('text'),  # 转发推文的文本通常是原推文内容
                'author': {
                    'username': original_author.get('username'),
                    'name': original_author.get('display_name') or original_author.get('name'),
                    'avatar': original_author.get('avatar_url'),
                    'verified': original_author.get('is_verified', False)
                },
                'time': tweet.get('timestamp'),  # 使用转发时间，原推文时间通常不可用
                'metrics': tweet.get('metrics', {}),  # 转发后的互动数据
            })
            
            # 保存转发操作信息
            primary_content['action'] = {
                'type': 'retweet',
                'user': self._extract_author_info(tweet.get('author', {})),
                'comment': retweeted.get('retweet_comment'),
                'timestamp': tweet.get('timestamp'),
                'retweeted_by': retweeted.get('retweeted_by')
            }
            
        elif tweet_type == 'reply':
            # 回复推文：主要内容就是回复内容（保持现有逻辑）
            primary_content['action'] = {
                'type': 'reply',
                'user': self._extract_author_info(tweet.get('author', {})),
                'timestamp': tweet.get('timestamp')
            }
        
        return primary_content
    
    def _clean_tweet_simple(self, tweet: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        简化的推文清理，用于向后兼容字段，不使用统一内容逻辑
        
        Args:
            tweet: 原始推文数据
            
        Returns:
            简单清理后的推文数据
        """
        if not tweet:
            return None
            
        # 过滤有用的外部链接
        useful_links = self._filter_useful_links(tweet.get('links', []))
        
        # 过滤无用的mentions
        useful_mentions = self._filter_useful_mentions(
            tweet.get('mentions', []),
            tweet.get('author', {}).get('username', '')
        )
        
        # 构建简单的推文对象（使用原始数据，不做统一处理）
        cleaned_tweet = {
            'id': tweet.get('tweet_id'),
            'text': tweet.get('text'),
            'author': self._extract_author_info(tweet.get('author', {})),
            'time': tweet.get('timestamp'),
            'metrics': tweet.get('metrics', {}),
            'media': tweet.get('media', []),
            'links': useful_links or [],
            'hashtags': tweet.get('hashtags', []),
            'mentions': useful_mentions or [],
        }
        
        # 推文类型
        tweet_type = tweet.get('tweet_type', 'normal')
        if tweet_type == 'normal':
            cleaned_tweet['type'] = 'original'
        else:
            cleaned_tweet['type'] = tweet_type
            
        return cleaned_tweet
    
    def _filter_useful_links(self, links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤有用的链接"""
        useful_links = []
        
        for link in links:
            url = link.get('url', '')
            text = link.get('text', '')
            link_type = link.get('type', '')
            
            # 跳过内部相对路径链接
            if url.startswith('/'):
                if (any(pattern in url for pattern in ['/status/', '/photo/', '/analytics']) or 
                    url.count('/') == 1):  # 单层路径如 /username
                    continue
            
            # 保留引用推文链接和外部链接
            if url.startswith('http'):
                # 保留引用推文链接
                if link_type == 'tweet' and ('twitter.com' in url or 'x.com' in url):
                    useful_links.append({
                        'url': url,
                        'text': text,
                        'type': link_type
                    })
                # 保留真正的外部链接
                elif 'twitter.com' not in url and 'x.com' not in url:
                    useful_links.append({
                        'url': url,
                        'text': text,
                        'type': link_type if link_type else 'external'
                    })
        
        return useful_links
    
    def _filter_useful_mentions(self, mentions: List[str], author_username: str = None) -> List[str]:
        """过滤无用的mentions（不包含自己，但保留引用推文中的所有mentions）"""
        # 对于引用推文，保留所有mentions，因为它们都是有意义的内容
        # 只有在主推文中才过滤掉自己的mention
        # author_username 参数保留以保持接口兼容性
        return mentions
    
    def _extract_author_info(self, author: Dict[str, Any]) -> Dict[str, Any]:
        """提取作者信息"""
        return {
            'username': author.get('username'),
            'name': author.get('display_name'),
            'avatar': author.get('avatar_url'),
            'verified': author.get('is_verified', False)
        }
    
    def _add_optional_fields(self, cleaned_tweet: Dict[str, Any], original_tweet: Dict[str, Any], 
                           useful_links: List[Dict[str, Any]], useful_mentions: List[str]):
        """添加字段，保持数据结构一致性"""
        
        # 媒体内容 - 优先使用继承的内容（引用推文的媒体）
        cleaned_tweet['media'] = cleaned_tweet.get('inherited_media', original_tweet.get('media', []))
        
        # 外部链接 - 合并继承的链接和有用链接
        inherited_links = cleaned_tweet.get('inherited_links', [])
        all_links = useful_links or []
        all_links.extend(inherited_links)
        cleaned_tweet['links'] = all_links
            
        # 话题标签 - 优先使用继承的标签
        cleaned_tweet['hashtags'] = cleaned_tweet.get('inherited_hashtags', original_tweet.get('hashtags', []))
            
        # 用户提及 - 优先使用继承的提及
        cleaned_tweet['mentions'] = cleaned_tweet.get('inherited_mentions', useful_mentions or [])
        
        # 清理临时的继承字段
        for key in ['inherited_links', 'inherited_media', 'inherited_hashtags', 'inherited_mentions']:
            cleaned_tweet.pop(key, None)
        
        # 推文类型 - 根据是否有action信息来决定
        if cleaned_tweet.get('action'):
            # 有action信息说明是引用、转发或回复，但主要内容已经统一
            action_type = cleaned_tweet['action']['type']
            cleaned_tweet['type'] = f"{action_type}_unified"  # 标识为统一格式
            cleaned_tweet['content_type'] = 'primary'  # 表示显示的是主要内容
        else:
            # 原创推文
            cleaned_tweet['type'] = 'original'
            cleaned_tweet['content_type'] = 'original'
        
        # 添加相关上下文（保持向后兼容）
        tweet_type = original_tweet.get('tweet_type', 'normal')
        
        if tweet_type == 'quote' and original_tweet.get('quoted_tweet'):
            # 为向后兼容保留quoted_tweet字段，但使用简化清理
            quoted_data = self._clean_tweet_simple(original_tweet.get('quoted_tweet'))
            if quoted_data:
                cleaned_tweet['quoted_tweet'] = quoted_data
        elif tweet_type == 'reply' and original_tweet.get('reply_context'):
            reply_context = original_tweet.get('reply_context')
            cleaned_reply_context = {}
            
            # Format reply context for clean output
            if reply_context.get('replying_to_text'):
                cleaned_reply_context['replying_to_text'] = reply_context['replying_to_text']
            
            if reply_context.get('replying_to_users'):
                cleaned_reply_context['replying_to_users'] = reply_context['replying_to_users']
            
            if reply_context.get('original_tweet_id'):
                cleaned_reply_context['original_tweet_id'] = reply_context['original_tweet_id']
                
            if reply_context.get('original_tweet_url'):
                cleaned_reply_context['original_tweet_link'] = {
                    'url': reply_context['original_tweet_url'],
                    'text': 'View original tweet',
                    'type': 'tweet'
                }
            
            if cleaned_reply_context:
                cleaned_tweet['reply_context'] = cleaned_reply_context
                
        elif tweet_type == 'retweet' and original_tweet.get('retweeted_tweet'):
            retweet_data = original_tweet.get('retweeted_tweet')
            cleaned_retweet_data = {}
            
            # Format retweet data for clean output
            if retweet_data.get('original_author'):
                cleaned_retweet_data['original_author'] = {
                    'username': retweet_data['original_author'].get('username'),
                    'name': retweet_data['original_author'].get('display_name')
                }
            
            if retweet_data.get('original_tweet_id'):
                cleaned_retweet_data['original_tweet_id'] = retweet_data['original_tweet_id']
                
            if retweet_data.get('original_tweet_url'):
                cleaned_retweet_data['original_tweet_link'] = {
                    'url': retweet_data['original_tweet_url'],
                    'text': 'View original tweet',
                    'type': 'tweet'
                }
            
            if retweet_data.get('retweet_comment'):
                cleaned_retweet_data['retweet_comment'] = retweet_data['retweet_comment']
            
            if retweet_data.get('retweeted_by'):
                cleaned_retweet_data['retweeted_by'] = retweet_data['retweeted_by']
            
            if cleaned_retweet_data:
                cleaned_tweet['retweeted_tweet'] = cleaned_retweet_data
    
    def _extract_page_context(self, page_context: Dict[str, Any]) -> Dict[str, Any]:
        """提取页面上下文信息"""
        return {
            'page_type': page_context.get('page_type'),
            'theme': page_context.get('theme'),
            'language': page_context.get('language')
        }
    
    def _extract_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """提取元数据信息"""
        return {
            'source': metadata.get('source'),
            'load_time': metadata.get('page_load_time'),
            'timestamp': metadata.get('timestamp')
        }


class ResponseFormatterFactory:
    """响应格式化器工厂类"""
    
    @staticmethod
    def create_tweet_formatter() -> TweetResponseFormatter:
        """创建推文响应格式化器"""
        return TweetResponseFormatter()