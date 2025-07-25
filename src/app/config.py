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
    # Cookie文件路径 - 使用统一路径管理器
    from .core.path_manager import get_cookie_file_path as _get_cookie_path
    _cookie_path = os.getenv('COOKIE_FILE_PATH', 'instance/twitter_cookies.json')
    COOKIE_FILE_PATH = _get_cookie_path(_cookie_path) if not os.path.isabs(_cookie_path) else _cookie_path
    
    # Flask配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # 服务配置
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '5100'))
    
    # API限制配置
    MAX_TWEETS_PER_REQUEST = int(os.getenv('MAX_TWEETS_PER_REQUEST', '100'))
    MAX_BATCH_SIZE = int(os.getenv('MAX_BATCH_SIZE', '50'))
    DEFAULT_TWEET_COUNT = int(os.getenv('DEFAULT_TWEET_COUNT', '10'))
    
    # 日志配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
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