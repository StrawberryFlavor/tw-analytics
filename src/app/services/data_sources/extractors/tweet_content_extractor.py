"""
推文内容提取器

负责提取推文的文本内容、作者信息、时间戳等基础信息
"""

import re
from typing import Dict, Optional
from playwright.async_api import Locator

from .base_extractor import BaseExtractor


class TweetContentExtractor(BaseExtractor):
    """推文内容提取器，专注于基础内容提取"""
    
    async def extract_text_content(self, tweet_element: Locator) -> str:
        """提取推文文本内容"""
        try:
            # 主要方法：tweetText
            text_element = await tweet_element.query_selector('[data-testid="tweetText"]')
            if text_element:
                return await text_element.text_content() or ""
            
            # 备用方法：查找带lang属性的文本内容
            lang_elements = await tweet_element.query_selector_all('[lang]')
            for element in lang_elements:
                text = await element.text_content()
                if text and len(text.strip()) > 10:  # 可能的推文内容
                    return text.strip()
            
        except Exception as e:
            self.logger.debug(f"Error extracting text: {e}")
        
        return ""
    
    async def extract_author_info(self, tweet_element: Locator) -> Dict[str, str]:
        """提取作者信息"""
        author = {
            "username": "unknown",
            "display_name": "Unknown",
            "avatar_url": None,
            "is_verified": False,
            "profile_url": None
        }
        
        try:
            # 方法1：从User-Name testid提取
            user_name_element = await tweet_element.query_selector('[data-testid="User-Name"]')
            if user_name_element:
                user_text = await user_name_element.text_content() or ""
                
                # 解析显示名和用户名
                if '@' in user_text:
                    parts = user_text.split('@')
                    author['display_name'] = parts[0].strip()
                    
                    username_part = parts[1].strip()
                    # 处理如"@username·2h"或"@username · 2h"的格式
                    username = re.split(r'[·•\s]', username_part)[0].strip()
                    author['username'] = username
            
            # 方法2：从头像图片提取
            avatar_img = await tweet_element.query_selector('img[src*="profile_images"]')
            if avatar_img:
                author['avatar_url'] = await avatar_img.get_attribute('src')
                
                # 尝试从头像URL提取用户名
                if not author['username'] or author['username'] == 'unknown':
                    avatar_alt = await avatar_img.get_attribute('alt')
                    if avatar_alt and 'profile image' in avatar_alt.lower():
                        # 从"username's profile image"模式提取
                        match = re.search(r"(.+?)'s profile", avatar_alt)
                        if match:
                            author['username'] = match.group(1)
            
            # 方法3：从个人资料链接提取
            profile_links = await tweet_element.query_selector_all('a[href^="/"]')
            for link in profile_links:
                href = await link.get_attribute('href')
                if href and not any(x in href for x in ['/status/', '/photo/', '/video/']):
                    # 可能是个人资料链接
                    username = href.strip('/').split('/')[0]
                    if username and len(username) <= 15:  # 有效的Twitter用户名长度
                        author['username'] = username
                        author['profile_url'] = f"https://twitter.com{href}"
                        break
            
            # 检查认证标志
            verified_badge = await tweet_element.query_selector('[aria-label*="Verified"]')
            author['is_verified'] = verified_badge is not None
            
        except Exception as e:
            self.logger.debug(f"Error extracting author info: {e}")
        
        return author
    
    async def extract_timestamp(self, tweet_element: Locator) -> Optional[str]:
        """提取推文时间戳"""
        try:
            # 查找时间元素
            time_elements = await tweet_element.query_selector_all('time')
            for time_elem in time_elements:
                datetime_attr = await time_elem.get_attribute('datetime')
                if datetime_attr:
                    return datetime_attr
            
        except Exception as e:
            self.logger.debug(f"Error extracting timestamp: {e}")
        
        return None
    
    async def extract_language(self, tweet_element: Locator) -> Optional[str]:
        """提取推文语言"""
        try:
            # 查找带lang属性的元素
            lang_element = await tweet_element.query_selector('[lang]')
            if lang_element:
                return await lang_element.get_attribute('lang')
                
        except Exception as e:
            self.logger.debug(f"Error extracting language: {e}")
        
        return None
    
    async def extract_location(self, tweet_element: Locator) -> Optional[str]:
        """提取推文位置信息"""
        try:
            # Twitter的位置信息通常较少暴露在DOM中
            # 这里可以扩展更复杂的位置提取逻辑
            location_element = await tweet_element.query_selector('[data-testid*="location"]')
            if location_element:
                return await location_element.text_content()
                
        except Exception as e:
            self.logger.debug(f"Error extracting location: {e}")
        
        return None