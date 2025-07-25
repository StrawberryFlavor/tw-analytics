"""
主推文数据提取器

整合所有子提取器，提供统一的推文数据提取接口
"""

from typing import Dict, Any, List, Optional
from playwright.async_api import Page, Locator

from .base_extractor import BaseExtractor
from .tweet_content_extractor import TweetContentExtractor
from .tweet_media_extractor import TweetMediaExtractor
from .tweet_metrics_extractor import TweetMetricsExtractor
from .tweet_type_detector import TweetTypeDetector
from .special_tweet_extractor import SpecialTweetExtractor


class TweetDataExtractor(BaseExtractor):
    """
    主推文数据提取器
    
    遵循单一职责原则，通过依赖注入整合各个专门的提取器
    """
    
    def __init__(self, page: Page):
        super().__init__(page)
        
        # 初始化各个专门的提取器
        self.content_extractor = TweetContentExtractor(page)
        self.media_extractor = TweetMediaExtractor(page)
        self.metrics_extractor = TweetMetricsExtractor(page)
        self.type_detector = TweetTypeDetector(page)
        self.special_extractor = SpecialTweetExtractor(page)
    
    async def extract_all_data(self, target_tweet_id: str = None) -> Dict[str, Any]:
        """
        提取页面上所有推文数据的主入口方法
        
        Args:
            target_tweet_id: 目标推文ID（可选）
            
        Returns:
            包含所有推文数据的字典
        """
        try:
            # 等待页面加载
            await self._wait_for_page_load()
            
            # 查找所有推文元素
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')
            self.logger.info(f"发现 {len(tweet_elements)} 个推文元素")
            
            if not tweet_elements:
                return self._create_empty_result()
            
            # 提取每个推文的数据
            all_tweets = []
            for i, tweet_element in enumerate(tweet_elements):
                tweet_data = await self._extract_single_tweet(tweet_element, str(i))
                if tweet_data and tweet_data.get('text'):  # 只添加有内容的推文
                    all_tweets.append(tweet_data)
            
            # 对推文进行分类
            categorized_result = self.type_detector.categorize_tweets(all_tweets, target_tweet_id)
            
            # 提取页面上下文信息
            page_context = await self._extract_page_context()
            
            # 构建最终结果
            result = {
                **categorized_result,
                'page_context': page_context,
                'extraction_metadata': {
                    'timestamp': self._get_current_timestamp(),
                    'total_tweets_found': len(all_tweets),
                    'target_tweet_id': target_tweet_id,
                    'source': 'playwright',
                    'page_load_time': getattr(self, '_page_load_time', None)
                }
            }
            
            self.logger.info(f"成功提取 {len(all_tweets)} 条推文数据")
            return result
            
        except Exception as e:
            self.logger.error(f"Data extraction failed: {e}")
            return self._create_error_result(str(e))
    
    async def _extract_single_tweet(self, tweet_element: Locator, tweet_index: str) -> Dict[str, Any]:
        """
        提取单个推文的完整数据
        
        Args:
            tweet_element: 推文DOM元素
            tweet_index: 推文索引
            
        Returns:
            推文数据字典
        """
        try:
            tweet_data = {}
            
            # 提取基础内容
            tweet_data["tweet_id"] = await self._extract_tweet_id(tweet_element)
            tweet_data["text"] = await self.content_extractor.extract_text_content(tweet_element)
            tweet_data["author"] = await self.content_extractor.extract_author_info(tweet_element)
            tweet_data["timestamp"] = await self.content_extractor.extract_timestamp(tweet_element)
            
            # 提取互动指标
            tweet_data["metrics"] = await self.metrics_extractor.extract_all_metrics(tweet_element)
            
            # 提取媒体内容
            tweet_data["media"] = await self.media_extractor.extract_media_content(tweet_element)
            tweet_data["links"] = await self.media_extractor.extract_links(tweet_element)
            tweet_data["hashtags"] = await self.media_extractor.extract_hashtags(tweet_element)
            tweet_data["mentions"] = await self.media_extractor.extract_mentions(tweet_element)
            
            # 确定推文类型并提取相关内容
            tweet_data["tweet_type"] = await self.type_detector.determine_tweet_type(tweet_element)
            tweet_data["semantic_type"] = self.type_detector.classify_tweet_type(tweet_data)
            
            # 根据类型提取特殊内容
            if tweet_data["tweet_type"] == "quote":
                tweet_data["quoted_tweet"] = await self.special_extractor.extract_quoted_tweet(tweet_element)
            elif tweet_data["tweet_type"] == "reply":
                tweet_data["reply_context"] = await self.special_extractor.extract_reply_context(tweet_element)
            elif tweet_data["tweet_type"] == "retweet":
                tweet_data["retweeted_tweet"] = await self.special_extractor.extract_retweeted_tweet(tweet_element)
            
            # 提取附加信息
            tweet_data["language"] = await self.content_extractor.extract_language(tweet_element)
            tweet_data["location"] = await self.content_extractor.extract_location(tweet_element)
            
            return tweet_data
            
        except Exception as e:
            self.logger.error(f"Failed to extract tweet {tweet_index}: {e}")
            return {"extraction_error": str(e)}
    
    async def _extract_tweet_id(self, tweet_element: Locator) -> Optional[str]:
        """提取推文ID"""
        try:
            # 方法1：从状态链接提取
            status_links = await tweet_element.query_selector_all('a[href*="/status/"]')
            for link in status_links:
                href = await link.get_attribute('href')
                if href:
                    import re
                    match = re.search(r'/status/(\d+)', href)
                    if match:
                        return match.group(1)
            
            # 方法2：从时间元素的链接提取
            time_links = await tweet_element.query_selector_all('time a')
            for link in time_links:
                href = await link.get_attribute('href')
                if href and '/status/' in href:
                    import re
                    match = re.search(r'/status/(\d+)', href)
                    if match:
                        return match.group(1)
            
        except Exception as e:
            self.logger.debug(f"提取推文ID失败: {e}")
        
        return None
    
    async def _wait_for_page_load(self):
        """等待页面加载完成"""
        try:
            # 等待推文元素出现
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
            
            # 等待网络空闲
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
                self.logger.debug("页面达到网络空闲状态")
            except Exception:
                # 如果网络空闲超时，继续执行
                self.logger.debug("网络空闲超时，但继续执行")
            
        except Exception as e:
            self.logger.warning(f"等待页面加载时出错: {e}")
    
    async def _extract_page_context(self) -> Dict[str, Any]:
        """提取页面上下文信息"""
        try:
            context = {
                'page_type': 'tweet',
                'theme': 'unknown',
                'language': 'unknown'
            }
            
            # 提取页面语言
            html_element = await self.page.query_selector('html')
            if html_element:
                lang = await html_element.get_attribute('lang')
                if lang:
                    context['language'] = lang
            
            # 提取主题信息（如果可用）
            theme_elements = await self.page.query_selector_all('[data-theme]')
            if theme_elements:
                theme = await theme_elements[0].get_attribute('data-theme')
                if theme:
                    context['theme'] = theme
            
            return context
            
        except Exception as e:
            self.logger.debug(f"提取页面上下文失败: {e}")
            return {'page_type': 'tweet', 'theme': 'unknown', 'language': 'unknown'}
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """创建空结果"""
        return {
            'primary_tweet': None,
            'thread_tweets': [],
            'related_tweets': [],
            'page_context': {'page_type': 'tweet', 'theme': 'unknown', 'language': 'unknown'},
            'extraction_metadata': {
                'timestamp': self._get_current_timestamp(),
                'total_tweets_found': 0,
                'source': 'playwright',
                'error': 'No tweets found'
            }
        }
    
    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'primary_tweet': None,
            'thread_tweets': [],
            'related_tweets': [],
            'page_context': {'page_type': 'tweet', 'theme': 'unknown', 'language': 'unknown'},
            'extraction_metadata': {
                'timestamp': self._get_current_timestamp(),
                'total_tweets_found': 0,
                'source': 'playwright',
                'error': error_message
            }
        }
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()