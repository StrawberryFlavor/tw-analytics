"""
Twitter浏览量提升服务 v2.0 - 简化版
基于twitter_booster.py，集成account_management模块，遵循KISS原则
"""

from .twitter_booster import MultiURLViewBooster, ViewBoosterConfig
from .proxy_pool import ProxyPool
from .task_manager import TaskManager, task_manager
from .fast_booster import FastViewBooster, FastBoosterConfig

# 重新导出account_management模块中的核心类 - 修复导入路径
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(src_path))

from account_management import AccountManager, AccountSwitcher
from account_management.models import Account, AccountStatus

__all__ = [
    # 核心业务类
    'MultiURLViewBooster',
    'ViewBoosterConfig',
    'FastViewBooster',
    'FastBoosterConfig',
    'ProxyPool',
    
    # 任务管理
    'TaskManager',
    'task_manager',
    
    # 账户管理（来自account_management模块）
    'Account',
    'AccountStatus',
    'AccountManager',
    'AccountSwitcher',
]

__version__ = '2.0.0'