"""
推文类型检测器

负责检测推文的类型（原创、引用、回复、转发等）和分类
"""

from datetime import datetime, timedelta
from typing import Dict, List
from playwright.async_api import Locator

from .base_extractor import BaseExtractor


class TweetTypeDetector(BaseExtractor):
    """推文类型检测器，专注于推文类型识别和分类"""
    
    async def determine_tweet_type(self, tweet_element: Locator) -> str:
        """确定推文类型，基于真实Twitter结构进行增强引用检测"""
        try:
            # 🔍 增强策略：首先检查多个tweetText元素（最可靠的指标）
            text_elements = await tweet_element.query_selector_all('[data-testid="tweetText"]')
            
            if len(text_elements) >= 2:
                return "quote"
            
            # 策略1：查找包含文本和用户信息的role="link"容器
            quote_link_containers = await tweet_element.query_selector_all('[role="link"][href*="/status/"]')
            
            for i, container in enumerate(quote_link_containers):
                href = await container.get_attribute('href')
                
                # 检查容器是否包含用户和文本内容（强引用指标）
                has_user_name = await container.query_selector('[data-testid="User-Name"]')
                has_text_content = await container.query_selector('div[dir="ltr"], span[dir="ltr"]')
                has_avatar = await container.query_selector('img[src*="profile_images"]')
                
                if (has_user_name or has_avatar) and has_text_content:
                    return "quote"
                
                # 备选：检查容器中的实质性文本内容
                container_text = await container.text_content()
                if container_text and len(container_text.strip()) > 30:
                    # 查找表明这是引用内容的模式
                    lines = container_text.strip().split('\n')
                    # 如果有多行且其中一行包含用户信息模式
                    for line in lines:
                        if line.strip() and any(pattern in line for pattern in ['@', '·', 'hour', 'min', 'ago']):
                            return "quote"
            
            # 策略2：查找嵌套的article结构
            nested_articles = await tweet_element.query_selector_all('article')
            if len(nested_articles) > 1:
                return "quote"
            
            # 策略3：查找多个User-Name元素（主推文 + 引用推文）
            user_elements = await tweet_element.query_selector_all('[data-testid="User-Name"]')
            if len(user_elements) >= 2:
                return "quote"
            
            # 策略4：在aria-labels中查找引用指标
            quote_indicators = await tweet_element.query_selector_all('*[aria-label*="Quote"], *[aria-label*="引用"]')
            if quote_indicators:
                return "quote"
            
            # 检查转发指标
            retweet_indicators = await tweet_element.query_selector_all('*[aria-label*="Retweeted"], *[aria-label*="转发"]')
            if retweet_indicators:
                return "retweet"
            
            # 检查回复指标
            # 注意：需要排除指标栏的误判（如 "13 回复、12 次转帖" 等）
            reply_indicators = await tweet_element.query_selector_all('*[aria-label*="Replying to"]')
            if reply_indicators:
                return "reply"
            
            # 对于中文"回复"，需要更精确的匹配，避免指标栏误判
            cn_reply_indicators = await tweet_element.query_selector_all('*[aria-label*="回复"]')
            for elem in cn_reply_indicators:
                aria_label = await elem.get_attribute('aria-label')
                if aria_label:
                    self.logger.debug(f"Found aria-label with '回复': {aria_label}")
                    # 排除指标栏（包含"次转帖"、"喜欢"、"次观看"等词汇）
                    if not any(metric in aria_label for metric in ['次转帖', '喜欢', '次观看', 'retweets', 'likes', 'views']):
                        self.logger.info(f"Detected as reply tweet due to aria-label: {aria_label}")
                        return "reply"
                    else:
                        self.logger.debug(f"Skipped metrics bar: {aria_label}")
        
        except Exception as e:
            self.logger.debug(f"Error determining tweet type: {e}")
        
        return "normal"
    
    def classify_tweet_type(self, tweet: Dict) -> str:
        """基于推文内容分类推文类型"""
        try:
            text = tweet.get('text', '').lower()
            author = tweet.get('author', {}).get('username', '')
            
            # 检查是否为线程推文
            if any(indicator in text for indicator in ['1/', '2/', '🧵', 'thread']):
                return 'thread'
            
            # 检查是否为公告推文
            if any(indicator in text for indicator in ['announcement', '公告', 'breaking', '重要']):
                return 'announcement'
            
            # 检查是否为营销推文
            if any(indicator in text for indicator in ['buy', 'sale', '购买', '销售', '优惠']):
                return 'promotional'
            
            # 检查是否为回复推文
            if text.startswith('@') or 'replying to' in text:
                return 'reply'
            
            # 默认为普通推文
            return 'normal'
            
        except Exception as e:
            self.logger.debug(f"Error classifying tweet type: {e}")
            return 'unknown'
    
    def is_thread_tweet(self, tweet: Dict, primary_tweet: Dict, primary_author: str, primary_time: str) -> bool:
        """判断是否为线程推文"""
        try:
            # 检查作者是否相同
            tweet_author = tweet.get('author', {}).get('username', '')
            if tweet_author != primary_author:
                return False
            
            # 检查时间接近性
            tweet_time = tweet.get('timestamp', '')
            if self._is_likely_reply_by_timing(tweet_time, primary_time):
                return True
            
            # 检查内容连续性
            tweet_text = tweet.get('text', '').lower()
            primary_text = primary_tweet.get('text', '').lower()
            
            # 线程指标
            thread_indicators = ['continued', '续', 'thread', '🧵', '/2', '/3', '/4']
            if any(indicator in tweet_text for indicator in thread_indicators):
                return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking thread tweet: {e}")
            return False
    
    def appears_to_be_reply(self, tweet: Dict, primary_tweet: Dict) -> bool:
        """基于内容检查推文是否看起来像回复"""
        text = tweet.get('text', '').strip().lower()
        primary_author = primary_tweet.get('author', {}).get('username', '').lower()
        
        # 检查回复指标
        reply_indicators = [
            f'@{primary_author}',  # 直接提及
            '回复',  # 中文"回复"
            'reply',
            '评论',  # 中文"评论"
        ]
        
        return any(indicator in text for indicator in reply_indicators)
    
    def _is_likely_reply_by_timing(self, tweet_time: str, primary_time: str) -> bool:
        """基于时间判断是否可能是回复"""
        try:
            if not tweet_time or not primary_time:
                return False
            
            # 解析时间戳
            tweet_dt = datetime.fromisoformat(tweet_time.replace('Z', '+00:00'))
            primary_dt = datetime.fromisoformat(primary_time.replace('Z', '+00:00'))
            
            # 计算时间差
            time_diff = abs((tweet_dt - primary_dt).total_seconds())
            
            # 如果在24小时内，可能是回复
            return time_diff <= 24 * 3600
            
        except Exception as e:
            self.logger.debug(f"Error parsing timestamps: {e}")
            return False
    
    def appears_to_be_primary_tweet(self, tweet: Dict) -> bool:
        """判断推文是否看起来像主推文"""
        try:
            # 检查推文质量指标
            text_length = len(tweet.get('text', ''))
            metrics = tweet.get('metrics', {})
            
            # 主推文通常有更多内容
            if text_length < 20:
                return False
            
            # 主推文通常有更多互动
            total_engagement = sum([
                metrics.get('likes', 0),
                metrics.get('retweets', 0),
                metrics.get('replies', 0)
            ])
            
            if total_engagement > 10:  # 有一定互动的推文更可能是主推文
                return True
            
            # 检查是否包含媒体（图片、视频等）
            if tweet.get('media') and len(tweet.get('media', [])) > 0:
                return True
            
            return text_length > 50  # 较长的文本更可能是主推文
            
        except Exception as e:
            self.logger.debug(f"Error checking primary tweet: {e}")
            return False
    
    def categorize_tweets(self, all_tweets: List[Dict], target_tweet_id: str = None) -> Dict:
        """对推文进行分类"""
        result = {
            'primary_tweet': None,
            'thread_tweets': [],
            'related_tweets': []
        }
        
        if not all_tweets:
            return result
        
        # 找到主推文
        primary_tweet = self._find_primary_tweet(all_tweets, target_tweet_id)
        if primary_tweet:
            result['primary_tweet'] = primary_tweet
            primary_author = primary_tweet.get('author', {}).get('username', '')
            primary_time = primary_tweet.get('timestamp', '')
            
            # 分类其他推文
            for tweet in all_tweets:
                if tweet == primary_tweet:
                    continue
                
                tweet_id = tweet.get('tweet_id')
                
                # 检查是否为线程推文
                if self.is_thread_tweet(tweet, primary_tweet, primary_author, primary_time):
                    result['thread_tweets'].append(tweet)
                else:
                    result['related_tweets'].append(tweet)
        else:
            # 如果没有找到明确的主推文，将第一个作为主推文
            result['primary_tweet'] = all_tweets[0]
            result['related_tweets'] = all_tweets[1:]
        
        return result
    
    def _find_primary_tweet(self, tweets: List[Dict], target_tweet_id: str = None) -> Dict:
        """找到主推文"""
        if not tweets:
            return None
        
        # 如果指定了目标推文ID，优先查找
        if target_tweet_id:
            for tweet in tweets:
                if tweet.get('tweet_id') == target_tweet_id:
                    return tweet
        
        # 基于质量评分找到最佳主推文
        best_tweet = None
        best_score = -1
        
        for tweet in tweets:
            score = self._calculate_tweet_score(tweet)
            if score > best_score:
                best_score = score
                best_tweet = tweet
        
        return best_tweet
    
    def _calculate_tweet_score(self, tweet: Dict) -> int:
        """计算推文质量评分"""
        score = 0
        
        # 文本长度评分
        text_length = len(tweet.get('text', ''))
        if text_length > 100:
            score += 3
        elif text_length > 50:
            score += 2
        elif text_length > 20:
            score += 1
        
        # 互动评分
        metrics = tweet.get('metrics', {})
        total_engagement = sum([
            metrics.get('likes', 0),
            metrics.get('retweets', 0),
            metrics.get('replies', 0)
        ])
        
        if total_engagement > 100:
            score += 5
        elif total_engagement > 10:
            score += 3
        elif total_engagement > 0:
            score += 1
        
        # 媒体内容评分
        if tweet.get('media') and len(tweet.get('media', [])) > 0:
            score += 2
        
        # 浏览量评分
        views = metrics.get('views', 0)
        if views > 10000:
            score += 3
        elif views > 1000:
            score += 2
        elif views > 0:
            score += 1
        
        return score