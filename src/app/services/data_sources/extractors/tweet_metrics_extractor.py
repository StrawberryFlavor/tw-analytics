"""
推文指标提取器

负责提取推文的各种互动指标，如点赞数、转发数、回复数等
"""

import re
from typing import Dict
from playwright.async_api import Locator

from .base_extractor import BaseExtractor
from .rate_limit_detector import rate_limit_detector


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
    
    VIEWS_SELECTORS = [
        'text=/\\d+\\s*Views?/i',
        'text=/\\d+\\s*浏览/i', 
        '[aria-label*="view" i]',
        '[aria-label*="浏览" i]'
    ]
    
    TIMESTAMP_SELECTORS = [
        'time',
        '[datetime]',
        'a[href*="/status/"]',
        '[data-testid*="time"]'
    ]
    
    VIEW_PATTERNS = [
        r'(\d+)\s*Views?\b',
        r'(\d+[.,]\d+[KMB万]?)\s*Views?\b',
        r'(\d+[KMB万])\s*Views?\b',
        r'(\d+)\s*(?:次?浏览|观看)'
    ]
    
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
            await self._wait_for_views_data(tweet_element)
            
            view_count = await self._extract_views_near_timestamp(tweet_element)
            if view_count > 0:
                return view_count
            
            view_count = await self._extract_views_from_elements(tweet_element)
            if view_count > 0:
                return view_count
            
            view_count = await self._extract_views_from_page_improved(tweet_element)
            if view_count > 0:
                return view_count
            
            return await self._extract_views_from_page_content(tweet_element)
        
        except Exception as e:
            self.logger.debug(f"Error in comprehensive view extraction: {e}")
            return 0
    
    async def _wait_for_views_data(self, tweet_element: Locator, max_wait_seconds: int = 3):
        """等待views数据完全加载，支持风控检测"""
        try:
            page = tweet_element.page
            
            for selector in self.VIEWS_SELECTORS:
                success = await rate_limit_detector.safe_wait_for_selector(
                    page, selector, timeout=max_wait_seconds * 1000, state='visible'
                )
                if success:
                    return
            
            # 如果没有找到views选择器，等待网络空闲
            try:
                await page.wait_for_load_state('networkidle', timeout=max_wait_seconds * 1000)
            except Exception as network_error:
                # 网络等待错误也可能触发风控
                if rate_limit_detector.is_rate_limited(network_error):
                    await rate_limit_detector.handle_rate_limit(network_error, "等待网络空闲状态")
            
        except Exception as e:
            self.logger.debug(f"Error waiting for views data: {e}")
    
    async def _extract_views_near_timestamp(self, tweet_element: Locator) -> int:
        """在时间戳附近精确查找views数据"""
        try:
            for selector in self.TIMESTAMP_SELECTORS:
                timestamp_elements = await tweet_element.query_selector_all(selector)
                
                for timestamp_element in timestamp_elements:
                    view_count = await self._search_views_in_container(timestamp_element)
                    if view_count > 0:
                        return view_count
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error extracting views near timestamp: {e}")
            return 0
    
    async def _search_views_in_container(self, container_element: Locator) -> int:
        """在指定容器及其父级容器中搜索views数据"""
        try:
            search_elements = [container_element]
            
            try:
                parent = await container_element.query_selector('xpath=..')
                if parent:
                    search_elements.append(parent)
                    grandparent = await parent.query_selector('xpath=..')
                    if grandparent:
                        search_elements.append(grandparent)
            except:
                pass
            
            for element in search_elements:
                text = await element.text_content()
                if not text:
                    continue
                
                for pattern in self.VIEW_PATTERNS:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for match in matches:
                        count = parse_count_text(match)
                        if count > 0:
                            return count
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error searching views in container: {e}")
            return 0
    
    async def _extract_views_from_elements(self, tweet_element: Locator) -> int:
        """从推文元素中提取views数据"""
        try:
            view_elements = await tweet_element.query_selector_all('*')
            
            for element in view_elements:
                text = await element.text_content()
                if not text:
                    continue
                
                text_lower = text.lower()
                if any(keyword in text_lower for keyword in ['view', '浏览', '观看', '查看']):
                    if re.search(r'\d+[.,]?\d*[KMB万千万亿]?\s*(?:view|浏览|观看|查看)', text, re.IGNORECASE):
                        count = parse_count_text(text)
                        if count > 0:
                            return count
                
                number_match = re.search(r'^([\d,\.]+[KMB万千万亿]?)\s*$', text.strip())
                if number_match:
                    count = parse_count_text(number_match.group(1))
                    if count > 1000:
                        element_html = await element.inner_html()
                        if 'analytics' in element_html.lower():
                            return count
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error extracting views from elements: {e}")
            return 0
    
    async def _extract_views_from_page_improved(self, tweet_element: Locator) -> int:
        """使用JavaScript提取views数据"""
        try:
            page = tweet_element.page
            
            js_views_extractor = r"""
            () => {
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: function(node) {
                            const text = node.textContent.toLowerCase();
                            return (text.includes('view') || text.includes('浏览')) 
                                ? NodeFilter.FILTER_ACCEPT 
                                : NodeFilter.FILTER_REJECT;
                        }
                    }
                );
                
                const viewsData = [];
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent;
                    
                    const patterns = [
                        /(\d+)\s*Views?\b/gi,
                        /(\d+[.,]\d+[KMB万]?)\s*Views?\b/gi,
                        /(\d+[KMB万])\s*Views?\b/gi,
                        /(\d+)\s*(?:次?浏览|观看)/gi
                    ];
                    
                    for (const pattern of patterns) {
                        const matches = text.match(pattern);
                        if (matches) {
                            for (const match of matches) {
                                const numberMatch = match.match(/(\d+(?:[.,]\d+)?[KMB万]?)/);
                                if (numberMatch) {
                                    viewsData.push({
                                        text: match.trim(),
                                        number: numberMatch[1]
                                    });
                                }
                            }
                        }
                    }
                }
                
                return viewsData;
            }
            """
            
            views_data = await page.evaluate(js_views_extractor)
            
            if views_data and len(views_data) > 0:
                for data in views_data:
                    count = parse_count_text(data['number'])
                    if count > 0:
                        return count
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error in improved page views extraction: {e}")
            return 0
    
    async def _extract_views_from_page_content(self, tweet_element: Locator) -> int:
        """从页面内容提取views数据"""
        try:
            page = tweet_element.page
            page_text = await page.content()
            
            for pattern in self.VIEW_PATTERNS:
                views_matches = re.findall(pattern, page_text, re.IGNORECASE)
                if views_matches:
                    for match in views_matches:
                        count = parse_count_text(match)
                        if count > 0:
                            return count
            
            return 0
            
        except Exception as e:
            self.logger.debug(f"Error extracting views from page content: {e}")
            return 0
    
    async def _extract_views_from_page_context(self, tweet_element: Locator) -> int:
        """从页面上下文（时间戳区域）提取views数据"""
        try:
            # 获取页面引用以搜索整个页面
            page = tweet_element.page
            
            # 更广泛的元素选择，包括所有可能包含views的元素
            all_elements = await page.query_selector_all('span, div, time, a')
            
            for element in all_elements:
                text = await element.text_content()
                if not text:
                    continue
                
                # 查找包含Views的文本
                if 'Views' in text or 'views' in text:
                    # 查找时间戳后的views模式
                    views_match = re.search(r'(\d+)\s*Views?\b', text, re.IGNORECASE)
                    if views_match:
                        count = int(views_match.group(1))
                        return count
                
                # 检查父元素或兄弟元素中的views
                try:
                    parent = await element.query_selector('xpath=..')
                    if parent:
                        parent_text = await parent.text_content()
                        if parent_text and 'Views' in parent_text:
                            parent_views_match = re.search(r'(\d+)\s*Views?\b', parent_text, re.IGNORECASE)
                            if parent_views_match:
                                count = int(parent_views_match.group(1))
                                self.logger.debug(f"Found views in parent context: '{parent_text}' -> {count}")
                                return count
                except:
                    pass
        
        except Exception as e:
            self.logger.debug(f"Error extracting views from page context: {e}")
        
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