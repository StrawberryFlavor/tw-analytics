"""Data sources module."""

from .base import BaseDataSource
from .twitter_api import TwitterAPISource
# from .playwright import PlaywrightSource  # 已移除，统一使用PlaywrightPooledSource
from .extractors import TweetDataExtractor
from .manager import DataSourceManager

__all__ = [
    'BaseDataSource',
    'TwitterAPISource', 
    # 'PlaywrightSource',  # 已移除，统一使用PlaywrightPooledSource
    'TweetDataExtractor',
    'DataSourceManager'
]