"""
Flask配置管理
"""

import os
from .core.path_manager import load_env_file

# 加载环境变量文件
load_env_file()


class Config:
    """基础配置"""
    
    # Twitter API配置
    TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
    
    # Twitter登录配置 (用于Playwright爬虫)
    TWITTER_USERNAME = os.getenv('TWITTER_USERNAME')
    TWITTER_PASSWORD = os.getenv('TWITTER_PASSWORD')
    TWITTER_EMAIL = os.getenv('TWITTER_EMAIL')  # 备用邮箱，用于验证
    
    # Playwright配置
    PLAYWRIGHT_HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
    PLAYWRIGHT_PROXY = os.getenv('PLAYWRIGHT_PROXY')  # 格式: http://127.0.0.1:7890
    # Cookie系统已移除，使用统一账户管理系统
    # from .core.path_manager import get_cookie_file_path as _get_cookie_path
    # _cookie_path = os.getenv('COOKIE_FILE_PATH', 'instance/twitter_cookies.json')
    # COOKIE_FILE_PATH = _get_cookie_path(_cookie_path) if not os.path.isabs(_cookie_path) else _cookie_path
    
    # Flask配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    # 服务配置
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '5100'))
    
    # API限制配置
    MAX_TWEETS_PER_REQUEST = int(os.getenv('MAX_TWEETS_PER_REQUEST', '100'))
    MAX_BATCH_SIZE = int(os.getenv('MAX_BATCH_SIZE', '50'))
    DEFAULT_TWEET_COUNT = int(os.getenv('DEFAULT_TWEET_COUNT', '10'))
    
    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Twitter/X 平台配置
    TWITTER_BASE_URL = os.getenv('TWITTER_BASE_URL', 'https://x.com')
    TWITTER_LEGACY_URL = os.getenv('TWITTER_LEGACY_URL', 'https://twitter.com')
    
    # Apify配置
    APIFY_ENABLE = os.getenv('APIFY_ENABLE', 'false').lower() == 'true'
    APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')
    APIFY_ACTOR_ID = os.getenv('APIFY_ACTOR_ID', 'apidojo/tweet-scraper')
    APIFY_TIMEOUT = int(os.getenv('APIFY_TIMEOUT', '120'))
    
    # 数据源优先级配置
    DATA_SOURCE_PRIORITY = os.getenv('DATA_SOURCE_PRIORITY', 'playwright,apify,twitter_api')
    
    # 🏊‍♂️ 浏览器池核心配置 (简化版)
    BROWSER_POOL_MIN_SIZE = int(os.getenv('BROWSER_POOL_MIN_SIZE', '2'))
    BROWSER_POOL_MAX_SIZE = int(os.getenv('BROWSER_POOL_MAX_SIZE', '6'))
    BROWSER_POOL_MAX_CONCURRENT_REQUESTS = int(os.getenv('BROWSER_POOL_MAX_CONCURRENT_REQUESTS', '3'))
    BROWSER_POOL_REQUEST_TIMEOUT = int(os.getenv('BROWSER_POOL_REQUEST_TIMEOUT', '120'))
    BROWSER_POOL_INSTANCE_LIFETIME = int(os.getenv('BROWSER_POOL_INSTANCE_LIFETIME', '1800'))
    
    # 🎭 反检测配置
    BROWSER_POOL_ROTATION_ENABLED = os.getenv('BROWSER_POOL_ROTATION_ENABLED', 'true').lower() == 'true'
    BROWSER_POOL_ANTI_DETECTION_LEVEL = os.getenv('BROWSER_POOL_ANTI_DETECTION_LEVEL', 'medium')
    
    # ⚙️ 智能计算的配置 (基于 INSTANCE_LIFETIME 自动推导)
    @classmethod
    def get_max_idle_time(cls):
        """最大空闲时间 = 实例生命周期 * 0.6"""
        return cls.BROWSER_POOL_INSTANCE_LIFETIME * 0.6
    
    @classmethod  
    def get_health_check_interval(cls):
        """健康检查间隔 = 实例生命周期 / 60 (更频繁的检查)"""
        return max(15.0, cls.BROWSER_POOL_INSTANCE_LIFETIME / 60)
    
    @classmethod
    def get_rotation_check_interval(cls):
        """轮换检查间隔 = 实例生命周期 / 12 (更频繁的轮换检查)"""
        return cls.BROWSER_POOL_INSTANCE_LIFETIME / 12
    
    @classmethod
    def get_max_usage_count(cls):
        """最大使用次数 (根据反检测级别调整)"""
        level_mapping = {
            'low': 15,     # 低级别：15次后轮换，防止驱动连接问题
            'medium': 10,  # 中级别：10次后轮换
            'high': 5      # 高级别：5次后频繁轮换
        }
        return level_mapping.get(cls.BROWSER_POOL_ANTI_DETECTION_LEVEL, 20)
    
    @classmethod
    def get_rotation_probability(cls):
        """轮换概率 (根据反检测级别调整)"""
        level_mapping = {
            'low': 0.02,    # 2% 概率
            'medium': 0.05, # 5% 概率  
            'high': 0.10    # 10% 概率
        }
        return level_mapping.get(cls.BROWSER_POOL_ANTI_DETECTION_LEVEL, 0.05)
    
    # 🔄 账户管理配置
    ACCOUNT_MANAGEMENT_ENABLED = os.getenv('ACCOUNT_MANAGEMENT_ENABLED', 'true').lower() == 'true'
    ACCOUNT_SWITCH_THRESHOLD = int(os.getenv('ACCOUNT_SWITCH_THRESHOLD', '100'))
    ACCOUNT_SWITCH_STRATEGY = os.getenv('ACCOUNT_SWITCH_STRATEGY', 'cycle')  # cycle, round_robin, random
    ACCOUNT_LOGIN_VERIFICATION = os.getenv('ACCOUNT_LOGIN_VERIFICATION', 'false').lower() == 'true'
    ACCOUNT_CONFIG_PATH = os.getenv('ACCOUNT_CONFIG_PATH', 'src/config/accounts.json')
    
    @classmethod
    def get_account_switch_threshold(cls):
        """获取账户切换阈值"""
        return cls.ACCOUNT_SWITCH_THRESHOLD
    
    # 验证必需的配置
    @classmethod
    def validate(cls):
        if not cls.TWITTER_BEARER_TOKEN:
            raise ValueError("TWITTER_BEARER_TOKEN环境变量未设置")


class DevelopmentConfig(Config):
    """开发配置"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """生产配置"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """测试配置"""
    DEBUG = True
    TESTING = True
    TWITTER_BEARER_TOKEN = "test-token"


# 配置映射
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(config_name='default'):
    """获取配置类"""
    return config_map.get(config_name, DevelopmentConfig)