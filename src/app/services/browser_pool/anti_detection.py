"""
反爬虫检测管理器
提供轻量级的反检测策略，避免被Twitter识别为自动化工具
"""

import random
from typing import Dict, Any


class AntiDetectionManager:
    """反检测管理器"""
    
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        ]
        
        self.viewports = [
            {'width': 1920, 'height': 1080},
            {'width': 1440, 'height': 900},
            {'width': 1366, 'height': 768},
            {'width': 1536, 'height': 864},
            {'width': 1600, 'height': 900},
        ]
        
        self.languages = ['en-US', 'en-GB', 'zh-CN', 'ja-JP']
        self.timezones = ['America/New_York', 'Europe/London', 'Asia/Shanghai', 'Asia/Tokyo']
    
    def get_random_config(self) -> Dict[str, Any]:
        """获取随机的浏览器配置"""
        return {
            'user_agent': random.choice(self.user_agents),
            'viewport': random.choice(self.viewports),
            'language': random.choice(self.languages),
            'timezone': random.choice(self.timezones),
        }
    
    def get_basic_stealth_script(self) -> str:
        """获取基础隐身脚本，移除webdriver痕迹"""
        return """
        // 基础反检测脚本
        (() => {
            // 移除webdriver标识
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // 伪装chrome对象
            window.chrome = window.chrome || {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 移除automation相关属性
            delete navigator.__proto__.webdriver;
            
            // 伪装插件信息
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 伪装languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
        })();
        """
    
    def get_random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0) -> float:
        """获取随机延迟时间"""
        return random.uniform(min_delay, max_delay)
    
    def should_add_human_delay(self, probability: float = 0.3) -> bool:
        """是否应该添加人类行为延迟"""
        return random.random() < probability