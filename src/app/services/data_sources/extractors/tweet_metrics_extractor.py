"""
推文指标提取器

负责提取推文的各种互动指标，如点赞数、转发数、回复数等
"""

import re
from typing import Dict
from playwright.async_api import Locator

from .base_extractor import BaseExtractor


def parse_count_text(text: str) -> int:
    """解析包含数字的文本，支持K、M等单位"""
    if not text:
        return 0
    
    # 使用正则提取数字和单位
    match = re.search(r'([\d,\.]+)\s*([KMB万千万亿]?)', text, re.IGNORECASE)
    if not match:
        return 0
    
    number_str = match.group(1).replace(',', '').replace('，', '')
    unit = match.group(2).upper() if match.group(2) else ''
    
    try:
        number = float(number_str)
        
        # 处理单位
        if unit in ['K', '千']:
            number *= 1000
        elif unit in ['M', '万']:
            number *= 10000
        elif unit in ['B', '亿']:
            number *= 100000000
        
        return int(number)
    except (ValueError, TypeError):
        return 0


class TweetMetricsExtractor(BaseExtractor):
    """推文指标提取器，专注于互动数据提取"""
    
    async def extract_all_metrics(self, tweet_element: Locator) -> Dict[str, int]:
        """提取推文的所有可见指标"""
        # 包含Twitter页面上显示的所有指标
        metrics = {
            "views": 0,
            "replies": 0,
            "retweets": 0,
            "likes": 0,
            "bookmarks": 0,
        }
        
        # 跟踪已找到的指标，避免用可疑数据覆盖
        found_metrics = set()
        
        try:
            # 方法1：从按钮aria-labels提取（最可靠）
            buttons = await tweet_element.query_selector_all('[role="button"]')
            for button in buttons:
                aria_label = await button.get_attribute('aria-label')
                if not aria_label:
                    continue
                
                aria_lower = aria_label.lower()
                count = parse_count_text(aria_label)
                
                # 严格的关键词匹配，只提取页面实际显示的指标
                if count > 0 and self._is_reasonable_metric_value(count):
                    if any(keyword in aria_lower for keyword in ['reply', '回复', '条回复']) and 'replies' not in found_metrics:
                        metrics['replies'] = count
                        found_metrics.add('replies')
                    elif any(keyword in aria_lower for keyword in ['retweet', '转发', '次转发']) and 'retweets' not in found_metrics:
                        metrics['retweets'] = count
                        found_metrics.add('retweets')
                    elif any(keyword in aria_lower for keyword in ['like', '喜欢', '次喜欢', '个赞']) and 'likes' not in found_metrics:
                        metrics['likes'] = count
                        found_metrics.add('likes')
                    elif any(keyword in aria_lower for keyword in ['bookmark', '书签', '收藏', '已添加书签']) and 'bookmarks' not in found_metrics:
                        metrics['bookmarks'] = count
                        found_metrics.add('bookmarks')
            
            # 方法2：从特定的data-testid提取
            await self._extract_metrics_from_testids(tweet_element, metrics, found_metrics)
            
            # 方法3：提取浏览量（单独处理，因为通常不在按钮中）
            if 'views' not in found_metrics:
                view_count = await self._extract_view_count_comprehensive(tweet_element)
                if view_count and view_count > 0 and self._is_reasonable_metric_value(view_count):
                    metrics['views'] = view_count
                    found_metrics.add('views')
            
            # 方法4：尝试检测引用数（如果页面确实显示）
            await self._try_extract_quotes(tweet_element, metrics, found_metrics)
            
            # 数据验证：检查异常重复的数值
            self._validate_and_clean_metrics(metrics)
            
        except Exception as e:
            self.logger.debug(f"Error extracting metrics: {e}")
        
        return metrics
    
    async def _extract_metrics_from_testids(self, tweet_element: Locator, metrics: Dict[str, int], found_metrics: set):
        """从data-testid属性提取指标数据"""
        testid_mapping = {
            'reply': 'replies',
            'retweet': 'retweets', 
            'like': 'likes',
            'bookmark': 'bookmarks'
        }
        
        for testid, metric_key in testid_mapping.items():
            if metric_key in found_metrics:
                continue
                
            try:
                # 查找对应的testid元素
                elements = await tweet_element.query_selector_all(f'[data-testid*="{testid}"]')
                for element in elements:
                    # 查找相邻的文本内容
                    parent = await element.query_selector('xpath=..')
                    if parent:
                        text = await parent.text_content()
                        if text:
                            count = parse_count_text(text)
                            if count > 0 and self._is_reasonable_metric_value(count):
                                metrics[metric_key] = count
                                found_metrics.add(metric_key)
                                break
            except Exception as e:
                self.logger.debug(f"Error extracting {metric_key} from testid: {e}")
    
    async def _try_extract_quotes(self, tweet_element: Locator, metrics: Dict[str, int], found_metrics: set):
        """尝试提取引用数（如果页面显示）"""
        if 'quotes' in found_metrics:
            return
            
        try:
            # 引用数通常较少显示，这里提供基本检测
            quote_elements = await tweet_element.query_selector_all('[aria-label*="quote"], [aria-label*="引用"]')
            for element in quote_elements:
                aria_label = await element.get_attribute('aria-label')
                if aria_label:
                    count = parse_count_text(aria_label)
                    if count > 0 and self._is_reasonable_metric_value(count):
                        metrics['quotes'] = count
                        found_metrics.add('quotes')
                        break
        except Exception as e:
            self.logger.debug(f"Error extracting quotes: {e}")
    
    async def _extract_view_count_comprehensive(self, tweet_element: Locator) -> int:
        """综合提取浏览量"""
        try:
            # 方法1：查找包含"views"或"浏览"的元素
            view_elements = await tweet_element.query_selector_all('*')
            
            for element in view_elements:
                text = await element.text_content()
                if not text:
                    continue
                
                text_lower = text.lower()
                
                # 检查是否包含浏览量关键词
                if any(keyword in text_lower for keyword in ['view', '浏览', '次浏览', '观看']):
                    # 查找数字模式
                    if re.search(r'\d+[.,]?\d*[KMB万千万亿]?\s*(?:view|浏览|次浏览|观看)', text, re.IGNORECASE):
                        count = parse_count_text(text)
                        if count > 0:
                            self.logger.debug(f"Found view count: '{text}' -> {count}")
                            return count
                
                # 特殊模式：纯数字后跟特定单位可能是浏览量
                number_match = re.search(r'^([\d,\.]+[KMB万千万亿]?)\s*$', text.strip())
                if number_match:
                    count = parse_count_text(number_match.group(1))
                    if count > 1000:  # 浏览量通常较大
                        # 验证这个元素的位置是否像浏览量
                        element_html = await element.inner_html()
                        if 'analytics' in element_html.lower():
                            self.logger.debug(f"Found view count in analytics: '{text}' -> {count}")
                            return count
                        
                        # 检查是否在正确的位置（通常在推文底部）
                        parent_text = ""
                        try:
                            parent = await element.query_selector('xpath=..')
                            if parent:
                                parent_text = await parent.text_content() or ""
                        except:
                            pass
                        
                        if any(indicator in parent_text.lower() for indicator in ['analytics', 'view', '浏览']):
                            self.logger.debug(f"Found view count with context: '{text}' -> {count}")
                            return count
        
        except Exception as e:
            self.logger.debug(f"Error in comprehensive view extraction: {e}")
        
        return 0
    
    async def _extract_metrics_from_engagement_bar(self, tweet_element: Locator, metrics: Dict[str, int]):
        """从互动栏提取指标"""
        try:
            # 查找包含互动按钮的容器
            engagement_containers = await tweet_element.query_selector_all('[role="group"], .css-175oi2r')
            
            for container in engagement_containers:
                container_text = await container.text_content()
                if not container_text:
                    continue
                
                # 检查是否包含典型的互动指标
                if any(keyword in container_text.lower() for keyword in ['reply', 'retweet', 'like', '回复', '转发', '喜欢']):
                    # 提取所有数字
                    numbers = re.findall(r'([\d,\.]+[KMB万千万亿]?)', container_text)
                    
                    # 尝试将数字与对应的操作匹配
                    for number_text in numbers:
                        count = parse_count_text(number_text)
                        if count > 0 and self._is_reasonable_metric_value(count):
                            # 根据位置和上下文推断指标类型
                            context = container_text[max(0, container_text.find(number_text) - 20):
                                                   container_text.find(number_text) + len(number_text) + 20].lower()
                            
                            if 'reply' in context or '回复' in context:
                                metrics['replies'] = max(metrics.get('replies', 0), count)
                            elif 'retweet' in context or '转发' in context:
                                metrics['retweets'] = max(metrics.get('retweets', 0), count)
                            elif 'like' in context or '喜欢' in context:
                                metrics['likes'] = max(metrics.get('likes', 0), count)
        
        except Exception as e:
            self.logger.debug(f"Error extracting engagement bar metrics: {e}")