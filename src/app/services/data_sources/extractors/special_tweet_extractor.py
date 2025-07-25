"""
特殊类型推文提取器

负责提取引用推文、回复推文、转发推文等特殊类型的推文数据
"""

import re
from typing import Dict, Any, Optional
from playwright.async_api import Locator

from .base_extractor import BaseExtractor


class SpecialTweetExtractor(BaseExtractor):
    """特殊推文提取器，专注于引用、回复、转发等特殊类型"""
    
    async def extract_quoted_tweet(self, tweet_element: Locator) -> Optional[Dict]:
        """提取引用推文数据，使用综合检测策略"""
        try:
            # 策略1：尝试找到嵌套的推文元素（最可靠）
            nested_tweet_selectors = [
                '[data-testid="tweet"] [data-testid="tweet"]',
                'article[data-testid="tweet"] article[data-testid="tweet"]',
                '[data-testid="tweet"] article'
            ]
            
            for selector in nested_tweet_selectors:
                nested_tweets = await tweet_element.query_selector_all(selector)
                if nested_tweets:
                    # 使用最后/最内层的元素，因为它可能是引用推文
                    quoted_element = nested_tweets[-1]
                    return await self._extract_quoted_tweet_data(quoted_element)
            
            # 策略2：查找带有嵌入内容的引用推文链接容器
            quote_link_containers = await tweet_element.query_selector_all('[role="link"][href*="/status/"]')
            for container in quote_link_containers:
                # 检查容器是否有推文样的内容
                has_tweet_text = await container.query_selector('[data-testid="tweetText"]')
                has_user_name = await container.query_selector('[data-testid="User-Name"]')
                has_tweet_content = await container.query_selector('div[dir="ltr"]')
                
                if has_tweet_text or (has_user_name and has_tweet_content):
                    return await self._extract_quoted_tweet_data(container)
            
            # 策略3：查找多个文本元素，表明有引用内容
            text_elements = await tweet_element.query_selector_all('[data-testid="tweetText"]')
            if len(text_elements) > 1:
                return await self._extract_quoted_tweet_from_multiple_texts(tweet_element, text_elements)
            
        except Exception as e:
            self.logger.warning(f"Error extracting quoted tweet: {e}")
        
        return None
    
    async def _extract_quoted_tweet_from_multiple_texts(self, tweet_element: Locator, text_elements) -> Optional[Dict]:
        """从多个文本元素中直接构造引用推文"""
        try:
            # 第二个文本元素是引用内容
            quoted_text_element = text_elements[1]
            quoted_text = await quoted_text_element.text_content()
            
            # 查找用户元素
            user_elements = await tweet_element.query_selector_all('[data-testid="User-Name"]')
            quoted_user_element = user_elements[1] if len(user_elements) > 1 else None
            quoted_user_text = await quoted_user_element.text_content() if quoted_user_element else ""
            
            # 提取状态链接
            status_links = await tweet_element.query_selector_all('a[href*="/status/"]')
            quoted_tweet_id = None
            
            # 找到属于引用推文的链接
            for link in status_links:
                href = await link.get_attribute('href')
                if href and '/status/' in href and '/photo/' not in href:
                    # 提取用户名和推文ID
                    match = re.search(r'/([^/]+)/status/(\d+)', href)
                    if match:
                        username = match.group(1)
                        tweet_id = match.group(2)
                        
                        # 根据用户信息判断是否为引用推文
                        if '@' in quoted_user_text and username in quoted_user_text:
                            quoted_tweet_id = tweet_id
                            break
            
            # 构造引用推文数据
            if quoted_text and quoted_user_text:
                # 解析用户信息
                quoted_author = {"username": "unknown", "display_name": "Unknown"}
                if '@' in quoted_user_text:
                    parts = quoted_user_text.split('@')
                    if len(parts) >= 2:
                        quoted_author['display_name'] = parts[0].strip()
                        username_part = parts[1].strip()
                        username = re.split(r'[·•\s]', username_part)[0].strip()
                        quoted_author['username'] = username
                
                # 提取提及
                mentions = []
                mention_pattern = r'@([a-zA-Z0-9_]+)'
                found_mentions = re.findall(mention_pattern, quoted_text)
                for mention in found_mentions:
                    mentions.append(f'@{mention}')
                mentions = list(dict.fromkeys(mentions))  # 去重
                
                # 提取标签
                hashtags = []
                hashtag_pattern = r'#(\w+)'
                found_hashtags = re.findall(hashtag_pattern, quoted_text)
                for hashtag in found_hashtags:
                    hashtags.append(f'#{hashtag}')
                
                # 构建链接数组
                links = []
                if quoted_tweet_id:
                    quoted_tweet_url = f"https://x.com/{quoted_author['username']}/status/{quoted_tweet_id}"
                    links.append({
                        'url': quoted_tweet_url,
                        'text': 'View quoted tweet',
                        'type': 'tweet'
                    })
                
                # 提取外部链接
                url_pattern = r'https?://[^\s]+'
                found_urls = re.findall(url_pattern, quoted_text)
                for url in found_urls:
                    links.append({
                        'url': url,
                        'text': url,
                        'type': 'external'
                    })
                
                quoted_data = {
                    "tweet_id": quoted_tweet_id,
                    "text": quoted_text,
                    "author": quoted_author,
                    "timestamp": None,
                    "metrics": {},
                    "media": [],
                    "links": links,
                    "hashtags": hashtags,
                    "mentions": mentions,
                    "tweet_type": "quoted"
                }
                
                return quoted_data
            
        except Exception as e:
            self.logger.debug(f"Error in multiple texts extraction: {e}")
        
        return None
    
    async def _extract_quoted_tweet_data(self, quoted_element: Locator) -> Dict[str, Any]:
        """从引用推文元素提取综合数据"""
        try:
            quoted_data = {
                "tweet_id": None,
                "text": "",
                "author": {},
                "timestamp": None,
                "metrics": {},
                "media": [],
                "links": [],
                "hashtags": [],
                "mentions": [],
                "tweet_type": "quoted"
            }
            
            # 提取文本内容
            text_element = await quoted_element.query_selector('[data-testid="tweetText"]')
            if text_element:
                quoted_data["text"] = await text_element.text_content() or ""
            else:
                # 备用方法：从lang属性元素提取
                lang_elements = await quoted_element.query_selector_all('[lang]')
                for elem in lang_elements:
                    text = await elem.text_content()
                    if text and len(text.strip()) > 5:
                        quoted_data["text"] = text.strip()
                        break
            
            # 提取作者信息
            user_name_element = await quoted_element.query_selector('[data-testid="User-Name"]')
            if user_name_element:
                user_text = await user_name_element.text_content() or ""
                if '@' in user_text:
                    parts = user_text.split('@')
                    quoted_data['author']['display_name'] = parts[0].strip()
                    username_part = parts[1].strip()
                    username = re.split(r'[·•\s]', username_part)[0].strip()
                    quoted_data['author']['username'] = username
            
            # 提取头像
            avatar_img = await quoted_element.query_selector('img[src*="profile_images"]')
            if avatar_img:
                quoted_data['author']['avatar_url'] = await avatar_img.get_attribute('src')
            
            # 提取推文ID
            status_links = await quoted_element.query_selector_all('a[href*="/status/"]')
            for link in status_links:
                href = await link.get_attribute('href')
                if href and '/status/' in href:
                    match = re.search(r'/([^/]+)/status/(\d+)', href)
                    if match:
                        quoted_data["tweet_id"] = match.group(2)
                        break
            
            return quoted_data
            
        except Exception as e:
            self.logger.debug(f"Error extracting quoted tweet data: {e}")
            return {}
    
    async def extract_reply_context(self, tweet_element: Locator) -> Optional[Dict]:
        """提取回复上下文"""
        try:
            reply_context = {
                "replying_to_text": None,
                "replying_to_users": [],
                "original_tweet_id": None,
                "original_tweet_url": None
            }
            
            # 查找"回复给"或"Replying to"文本
            replying_elements = await tweet_element.query_selector_all('*[aria-label*="Replying"], *[aria-label*="回复"]')
            for element in replying_elements:
                aria_label = await element.get_attribute('aria-label')
                if aria_label:
                    reply_context["replying_to_text"] = aria_label
                    break
            
            # 查找被回复的用户链接
            user_links = await tweet_element.query_selector_all('a[href^="/"]')
            for link in user_links:
                href = await link.get_attribute('href')
                text = await link.text_content()
                
                if href and text and text.startswith('@'):
                    # 排除状态、话题等链接
                    if not any(x in href for x in ['/status/', '/hashtag/', '/photo/']):
                        reply_context["replying_to_users"].append(text)
            
            # 查找原推文链接
            status_links = await tweet_element.query_selector_all('a[href*="/status/"]')
            for link in status_links:
                href = await link.get_attribute('href')
                if href:
                    match = re.search(r'/([^/]+)/status/(\d+)', href)
                    if match:
                        reply_context["original_tweet_id"] = match.group(2)
                        reply_context["original_tweet_url"] = f"https://x.com{href}" if href.startswith('/') else href
                        break
            
            # 如果找到有意义的信息就返回
            if any(v for v in reply_context.values() if v):
                return reply_context
            
        except Exception as e:
            self.logger.debug(f"Error extracting reply context: {e}")
        
        return None
    
    async def extract_retweeted_tweet(self, tweet_element: Locator) -> Optional[Dict]:
        """提取转发推文数据"""
        try:
            retweet_data = {
                "original_tweet_id": None,
                "original_tweet_url": None,
                "original_author": {},
                "retweet_comment": None,
                "retweeted_by": None
            }
            
            # 方法1：从转发文本中提取原作者信息
            retweet_text_elements = await tweet_element.query_selector_all('*[aria-label*="retweeted"], *[aria-label*="转发"]')
            for element in retweet_text_elements:
                aria_label = await element.get_attribute('aria-label')
                if aria_label:
                    # 提取用户名模式
                    user_pattern = r'([a-zA-Z0-9_]+)\s*(?:retweeted|转发了)'
                    match = re.search(user_pattern, aria_label, re.IGNORECASE)
                    if match:
                        original_username = match.group(1)
                        retweet_data["original_author"]["username"] = original_username
            
            # 方法2：查找原推文内容
            original_tweet_elements = await tweet_element.query_selector_all('[data-testid="tweet"] [data-testid="tweet"]')
            if original_tweet_elements:
                original_element = original_tweet_elements[0]
                
                # 提取原作者
                original_user_elements = await original_element.query_selector_all('[data-testid="User-Name"]')
                if original_user_elements:
                    user_text = await original_user_elements[0].text_content()
                    if user_text and '@' in user_text:
                        parts = user_text.split('@')
                        if len(parts) >= 2:
                            retweet_data["original_author"]["display_name"] = parts[0].strip()
                            username_part = parts[1].strip()
                            username = re.split(r'[·•\s]', username_part)[0].strip()
                            retweet_data["original_author"]["username"] = username
                
                # 提取原推文ID
                original_status_links = await original_element.query_selector_all('a[href*="/status/"]')
                for link in original_status_links:
                    href = await link.get_attribute('href')
                    if href and '/status/' in href:
                        match = re.search(r'/([^/]+)/status/(\d+)', href)
                        if match:
                            username = match.group(1)
                            tweet_id = match.group(2)
                            if username == retweet_data["original_author"].get("username"):
                                retweet_data["original_tweet_id"] = tweet_id
                                retweet_data["original_tweet_url"] = f"https://x.com{href}" if href.startswith('/') else href
                                break
            
            # 方法3：检查带评论的引用转发
            text_elements = await tweet_element.query_selector_all('[data-testid="tweetText"]')
            if len(text_elements) > 1:
                comment_text = await text_elements[0].text_content()
                if comment_text and comment_text.strip():
                    retweet_data["retweet_comment"] = comment_text.strip()
            
            # 如果找到有意义的信息就返回
            if any(v for v in retweet_data.values() if v):
                return retweet_data
            
        except Exception as e:
            self.logger.debug(f"Error extracting retweeted tweet: {e}")
        
        return None