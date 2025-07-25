"""
推文媒体提取器

负责提取推文中的媒体内容、链接、标签和提及等
"""

from typing import List, Dict, Any
from playwright.async_api import Locator

from .base_extractor import BaseExtractor


class TweetMediaExtractor(BaseExtractor):
    """推文媒体提取器，专注于媒体内容和链接提取"""
    
    async def extract_media_content(self, tweet_element: Locator) -> List[Dict[str, Any]]:
        """提取推文中的所有媒体内容"""
        media_items = []
        
        try:
            # 提取图片
            images = await tweet_element.query_selector_all('img[src*="/media/"]')
            for img in images:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt')
                if src:
                    media_items.append({
                        'type': 'image',
                        'url': src,
                        'alt_text': alt,
                        'format': 'jpg' if 'jpg' in src else 'png' if 'png' in src else 'unknown'
                    })
            
            # 提取视频
            videos = await tweet_element.query_selector_all('video')
            for video in videos:
                poster = await video.get_attribute('poster')
                src = await video.get_attribute('src')
                media_items.append({
                    'type': 'video',
                    'poster_url': poster,
                    'video_url': src
                })
            
            # 提取GIF（通常以视频形式呈现）
            gif_containers = await tweet_element.query_selector_all('[data-testid*="gif"]')
            for _ in gif_containers:
                # GIF比较复杂，提取能获取的信息
                media_items.append({
                    'type': 'gif',
                    'container_found': True
                })
        
        except Exception as e:
            self.logger.debug(f"Error extracting media: {e}")
        
        return media_items
    
    async def extract_links(self, tweet_element: Locator) -> List[Dict[str, str]]:
        """提取推文中的所有链接"""
        links = []
        
        try:
            link_elements = await tweet_element.query_selector_all('a[href]')
            for link in link_elements:
                href = await link.get_attribute('href')
                text = await link.text_content()
                
                if href and not href.startswith('#'):  # 跳过标签链接
                    # 确定链接类型
                    link_type = 'external'
                    if 'twitter.com' in href or 'x.com' in href:
                        if '/status/' in href:
                            link_type = 'tweet'
                        elif '/photo/' in href:
                            link_type = 'photo'
                        else:
                            link_type = 'profile'
                    
                    links.append({
                        'url': href,
                        'text': text,
                        'type': link_type
                    })
        
        except Exception as e:
            self.logger.debug(f"Error extracting links: {e}")
        
        return links
    
    async def extract_hashtags(self, tweet_element: Locator) -> List[str]:
        """提取推文中的标签"""
        hashtags = []
        
        try:
            hashtag_links = await tweet_element.query_selector_all('a[href*="/hashtag/"]')
            for link in hashtag_links:
                text = await link.text_content()
                if text and text.startswith('#'):
                    hashtags.append(text)
        
        except Exception as e:
            self.logger.debug(f"Error extracting hashtags: {e}")
        
        return hashtags
    
    async def extract_mentions(self, tweet_element: Locator) -> List[str]:
        """提取推文中的用户提及"""
        mentions = []
        
        try:
            # 在链接中查找@提及
            mention_links = await tweet_element.query_selector_all('a[href^="/"]')
            for link in mention_links:
                text = await link.text_content()
                href = await link.get_attribute('href')
                
                if text and text.startswith('@'):
                    mentions.append(text)
                elif href and not any(x in href for x in ['/status/', '/hashtag/', '/photo/']):
                    # 可能是没有@符号的用户提及
                    username = href.strip('/').split('/')[0]
                    if username and len(username) <= 15:
                        mentions.append(f'@{username}')
        
        except Exception as e:
            self.logger.debug(f"Error extracting mentions: {e}")
        
        return list(set(mentions))  # 去重