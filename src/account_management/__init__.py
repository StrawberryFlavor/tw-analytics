"""
Twitter账户管理系统

遵循SOLID原则的多账户管理解决方案：
- 单一职责：每个模块只负责特定功能
- 开闭原则：支持扩展新的存储方式和账户类型
- 里氏替换：接口实现可以互相替换
- 接口隔离：最小化接口设计
- 依赖倒置：依赖抽象而非具体实现
"""

from .models import Account, AccountStatus
from .parser import AccountParser
from .manager import AccountManager
from .switcher import AccountSwitcher
from .storage import IAccountStorage, JsonAccountStorage

__all__ = [
    'Account',
    'AccountStatus', 
    'AccountParser',
    'AccountManager',
    'AccountSwitcher',
    'IAccountStorage',
    'JsonAccountStorage'
]