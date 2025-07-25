"""
Twitter API异常定义
"""


class TwitterException(Exception):
    """Twitter API基础异常"""
    pass


class TwitterAuthException(TwitterException):
    """Twitter认证异常"""
    pass


class TwitterRateLimitException(TwitterException):
    """Twitter限流异常"""
    pass


class TwitterNotFoundException(TwitterException):
    """Twitter资源未找到异常"""
    pass