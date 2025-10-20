"""
Twitter风控检测和等待机制
"""

import os
import asyncio
import logging
from typing import Optional, Union
from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


class TwitterRateLimitDetector:
    """Twitter风控检测和处理器"""
    
    def __init__(self):
        load_dotenv()
        self.logger = logging.getLogger(__name__)
        
        # 从环境变量读取配置
        self.detection_enabled = os.getenv('TWITTER_RATE_LIMIT_DETECTION', 'true').lower() == 'true'
        self.smart_detection_enabled = os.getenv('TWITTER_RATE_LIMIT_SMART_DETECTION', 'true').lower() == 'true'
        self.wait_time = float(os.getenv('TWITTER_RATE_LIMIT_WAIT_TIME', '300'))  # 默认5分钟
        self.max_retries = int(os.getenv('TWITTER_RATE_LIMIT_MAX_RETRIES', '3'))
        
        # 风控检测关键词
        self.rate_limit_keywords = [
            'timeout',
            'Timeout',
            'rate limit',
            'rate_limit', 
            'Rate limit',
            'too many requests',
            'temporarily unavailable',
            'service unavailable'
        ]
        
        self.logger.info(f"风控检测器已初始化 - 启用: {self.detection_enabled}, 智能检测: {self.smart_detection_enabled}, 等待时间: {self.wait_time/60:.1f}分钟")
    
    def is_rate_limited(self, error: Union[str, Exception]) -> bool:
        """
        检测错误是否为风控相关
        
        Args:
            error: 错误信息或异常对象
            
        Returns:
            是否检测到风控
        """
        if not self.detection_enabled:
            return False
        
        error_str = str(error).lower()
        
        # 检查是否包含风控关键词
        for keyword in self.rate_limit_keywords:
            if keyword.lower() in error_str:
                return True
        
        # 特殊检查Playwright超时错误
        if isinstance(error, PlaywrightTimeoutError):
            return True
        
        return False
    
    async def handle_rate_limit(self, error: Union[str, Exception], context: str = "") -> None:
        """
        处理风控检测到的情况
        
        Args:
            error: 检测到的错误
            context: 上下文信息
        """
        if not self.is_rate_limited(error):
            return
        
        self.logger.error(f"检测到 Twitter 风控: {error}")
        if context:
            self.logger.warning(f"上下文: {context}")
        
        self.logger.warning(f"⏰ 启动风控等待机制，等待 {self.wait_time/60:.1f} 分钟以避开检测...")
        
        # 分段等待，每分钟输出一次进度
        total_minutes = int(self.wait_time // 60)
        remaining_seconds = self.wait_time % 60
        
        for minute in range(total_minutes):
            await asyncio.sleep(60)
            remaining_min = total_minutes - minute - 1
            self.logger.info(f"⏳ 风控等待中... 剩余 {remaining_min} 分钟")
        
        if remaining_seconds > 0:
            await asyncio.sleep(remaining_seconds)
        
        self.logger.info("风控等待完成，继续执行")
    
    async def _check_if_actual_rate_limit(self, page, error: Exception) -> bool:
        """
        检查是否是真正的风控，而不是权限限制或其他错误
        
        Args:
            page: Playwright页面对象
            error: 捕获的异常
            
        Returns:
            是否是真正的风控
        """
        try:
            # 如果没有启用智能检测，使用基础检测
            if not self.smart_detection_enabled:
                return self.is_rate_limited(error)
            
            # 首先基础检查是否包含超时关键词
            if not self.is_rate_limited(error):
                return False
            
            # 获取页面内容进行上下文分析
            page_url = page.url
            
            # 等待页面内容加载，给它一些时间
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=3000)
            except:
                pass  # 即使等待失败也要继续分析
            
            # 尝试获取页面的实际文本内容
            page_text = ""
            
            try:
                # 首先获取完整HTML内容
                html_content = await page.content()
                
                # 使用更强的文本提取
                import re
                # 移除script和style标签
                clean_html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
                
                # 移除HTML标签，但保留文本内容
                page_text = re.sub(r'<[^>]+>', ' ', clean_html)
                # 清理多余的空白字符
                page_text = re.sub(r'\s+', ' ', page_text).strip()
                
                # 如果提取的文本主要是CSS样式，尝试其他方法
                css_indicators = ['body {', '<style>', 'overflow-y:', 'background-color:', 'font-family:', '.errorContainer']
                is_mainly_css = (
                    any(page_text.startswith(indicator) for indicator in css_indicators) or
                    len([word for word in page_text.split()[:20] if any(char in word for char in '{}:;#.')]) > 10 or
                    page_text.count('{') + page_text.count('}') > 5
                )
                
                if is_mainly_css:
                    # 尝试JavaScript方法获取实际可见文本
                    try:
                        js_text = await page.evaluate('''() => {
                            // 优先获取body的可见文本
                            let text = document.body.innerText || document.body.textContent || '';
                            
                            // 如果没有获取到文本，尝试特定选择器
                            if (!text || text.trim().length < 10) {
                                const errorSelectors = [
                                    '.errorContainer',
                                    '[data-testid="error"]', 
                                    '.error-message',
                                    'h1', 'h2', 'h3',
                                    '.primaryText',
                                    'div[role="main"]',
                                    'main', 'article'
                                ];
                                
                                for (const selector of errorSelectors) {
                                    const elem = document.querySelector(selector);
                                    if (elem && elem.textContent && elem.textContent.trim().length > 5) {
                                        return elem.textContent.trim();
                                    }
                                }
                            }
                            
                            return text.trim();
                        }''')
                        
                        if js_text and len(js_text.strip()) > 10:
                            page_text = js_text.strip()
                    except:
                        pass
                        
            except Exception as e:
                self.logger.debug(f"页面内容提取失败: {e}")
                # 使用备用方法
                try:
                    page_text = await page.text_content('body') or ""
                except:
                    page_text = ""
            
            # 非风控的明确标识
            non_rate_limit_indicators = [
                # 页面不存在 (英文优先)
                "this page doesn't exist",
                "page doesn't exist", 
                "doesn't exist",
                "page not found",
                "not found",
                "404",
                "该页面不存在",
                "唔...该页面不存在",
                
                # 权限限制 (英文优先)
                "you can't view this tweet",
                "can't view this tweet",
                "protected tweets",
                "these tweets are protected",
                "account owner limits who can view",
                "limits who can view their tweets",
                "你无法查看这个帖子",
                "该账号所有者限制了可以查看其帖子的用户",
                "这些推文受到保护",
                
                # 推文状态问题 (英文优先)
                "this tweet is unavailable",
                "tweet is unavailable",
                "tweet unavailable",
                "this tweet was deleted",
                "tweet was deleted", 
                "tweet deleted",
                "推文已删除",
                "this tweet is from a suspended account",
                "tweet is from a suspended account",
                "from a suspended account",
                "suspended account",
                "account suspended",
                "account has been suspended",
                "User not found",
                "user not found",
                
                # 账号冻结相关 (中英双语)
                "这个帖子来自一个被冻结的账号",
                "帖子来自一个被冻结的账号",
                "来自一个被冻结的账号", 
                "被冻结的账号",
                "账号被冻结",
                "this tweet is from a frozen account",
                "tweet is from a frozen account",
                "from a frozen account",
                "frozen account",
                "account has been frozen",
                "account frozen",
                
                # 登录相关 - 需要更精确的匹配
                "sign in to twitter",
                "log in to twitter",
                "sign in to view",
                "log in to view",
                "you need to sign in",
                "please sign in",
                "please log in",
                "登录到Twitter",
                "登录以查看",
                
                # 地区限制 (英文优先)
                "not available in your country",
                "content is not available",
                "不在您所在的国家/地区提供"
            ]
            
            # 可能是风控的标识（需要结合其他条件判断）
            potential_rate_limit_indicators = [
                # 通用错误 - 如果没有推文内容，则可能是风控
                "something went wrong",
                "something went wrong. try reloading",
                "try again",
                "reload",
                "retry",
                
                # JavaScript/浏览器相关错误 - 如果没有推文内容，则可能是风控
                "javascript is not available",
                "javascript is disabled",
                "please enable javascript",
                "switch to a supported browser",
                "supported browser",
                "enable javascript"
            ]
            
            # 检查页面内容是否包含非风控标识
            if page_text and len(page_text.strip()) > 5:
                page_lower = page_text.lower()
                # 记录页面内容片段便于调试
                content_preview = page_text[:500].replace('\n', ' ').strip()
                self.logger.info(f"页面内容预览: {content_preview}")
                
                # 首先检查是否包含明确的非风控标识
                for indicator in non_rate_limit_indicators:
                    if indicator.lower() in page_lower:
                        self.logger.info(f"检测到非风控错误标识: '{indicator}' - 不是风控")
                        return False
                
                # 检查是否包含可能的风控标识
                has_potential_indicator = False
                detected_potential = []
                for indicator in potential_rate_limit_indicators:
                    if indicator.lower() in page_lower:
                        has_potential_indicator = True
                        detected_potential.append(indicator)
                
                # 如果包含可能的风控标识，需要进一步判断
                if has_potential_indicator:
                    # 检查是否有推文内容
                    try:
                        tweet_elements = await page.query_selector_all('[data-testid="tweet"]')
                        has_tweet_content = len(tweet_elements) > 0
                    except:
                        has_tweet_content = False
                    
                    if not has_tweet_content:
                        # 没有推文内容 + 错误消息 = 很可能是风控
                        self.logger.warning(f"检测到可疑标识 '{', '.join(detected_potential)}' 且无推文内容 - 判定为风控")
                        return True
                    else:
                        # 有推文内容 + 错误消息 = 可能只是临时错误
                        self.logger.info(f"ℹ️  检测到错误标识但有推文内容 - 不是风控")
                        return False
            else:
                self.logger.warning(f"无法获取页面内容或内容过短: {len(page_text) if page_text else 0} 字符")
            
            # 检查URL是否正常（如果被重定向到登录页等）
            if 'login' in page_url.lower() or 'signin' in page_url.lower():
                self.logger.info(f"页面被重定向到登录页: {page_url} - 不是风控")
                return False
            
            # 如果没有发现非风控标识，且是超时错误，则认为可能是风控
            self.logger.warning(f"超时错误但未发现非风控标识，可能是真实风控: {error}")
            return True
            
        except Exception as check_error:
            # 检查过程出错，为安全起见不认为是风控
            self.logger.warning(f"页面上下文检查失败，保守处理不认为是风控: {check_error}")
            return False
    
    async def safe_wait_for_selector(self, page, selector: str, timeout: int = 5000, **kwargs) -> bool:
        """
        带风控检测的安全等待选择器
        
        Args:
            page: Playwright页面对象
            selector: 选择器
            timeout: 超时时间（毫秒）
            **kwargs: 其他参数
            
        Returns:
            是否成功找到元素
        """
        try:
            await page.wait_for_selector(selector, timeout=timeout, **kwargs)
            return True
        except Exception as e:
            # 检查页面上下文以确定是否真的是风控
            is_actual_rate_limit = await self._check_if_actual_rate_limit(page, e)
            
            if is_actual_rate_limit:
                # 抛出风控异常，由上层决定如何处理
                class RateLimitDetectedError(Exception):
                    def __init__(self, message: str, wait_time: int = 300):
                        super().__init__(message)
                        self.wait_time = wait_time
                        
                raise RateLimitDetectedError(
                    f"检测到Twitter风控: {str(e)}",
                    wait_time=int(self.wait_time)
                )
            else:
                # 非风控错误（如权限限制、推文删除等），直接抛出
                raise e
    
    def get_wait_time_minutes(self) -> float:
        """获取等待时间（分钟）"""
        return self.wait_time / 60
    
    def is_enabled(self) -> bool:
        """检查风控检测是否启用"""
        return self.detection_enabled


# 全局实例
rate_limit_detector = TwitterRateLimitDetector()
