"""
账户管理器

遵循单一职责原则，负责账户的统一管理
"""

import logging
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timedelta
import random

from .models import Account, AccountStatus
from .parser import AccountParser, AccountParseError
from .storage import IAccountStorage, JsonAccountStorage

logger = logging.getLogger(__name__)


class AccountManagerError(Exception):
    """账户管理器异常"""
    pass


class AccountManager:
    """
    账户管理器
    
    提供账户的增删改查、状态管理、负载均衡等功能
    """
    
    def __init__(self, storage: IAccountStorage = None):
        """
        初始化账户管理器
        
        Args:
            storage: 存储接口实现，默认使用JSON存储
        """
        self.storage = storage or JsonAccountStorage()
        self._accounts_cache: List[Account] = []
        self._cache_updated_at: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # 缓存5分钟
    
    def _refresh_cache(self, force: bool = False) -> None:
        """刷新账户缓存"""
        if (force or 
            self._cache_updated_at is None or 
            datetime.now() - self._cache_updated_at > self._cache_ttl):
            
            self._accounts_cache = self.storage.load_accounts()
            self._cache_updated_at = datetime.now()
            logger.debug(f"账户缓存已刷新，共 {len(self._accounts_cache)} 个账户")
    
    def _invalidate_cache(self) -> None:
        """清除缓存"""
        self._cache_updated_at = None
    
    def import_accounts_from_strings(self, account_strings: List[str], 
                                   skip_errors: bool = True) -> Dict[str, Any]:
        """
        从字符串列表导入账户
        
        Args:
            account_strings: 账户字符串列表
            skip_errors: 是否跳过解析错误的账户
            
        Returns:
            dict: 导入结果统计
        """
        result = {
            'total': len(account_strings),
            'success': 0,
            'failed': 0,
            'duplicated': 0,
            'errors': []
        }
        
        try:
            # 解析账户
            accounts = AccountParser.parse_batch_accounts(account_strings, skip_errors=skip_errors)
            
            # 获取现有账户
            existing_accounts = self.get_all_accounts()
            existing_usernames = {acc.username for acc in existing_accounts}
            
            # 处理每个账户
            new_accounts = []
            for account in accounts:
                if account.username in existing_usernames:
                    result['duplicated'] += 1
                    logger.warning(f"账户 {account.username} 已存在，跳过")
                    continue
                
                new_accounts.append(account)
                result['success'] += 1
            
            # 批量保存新账户
            if new_accounts:
                all_accounts = existing_accounts + new_accounts
                if self.storage.save_accounts(all_accounts):
                    self._invalidate_cache()
                    logger.info(f"成功导入 {len(new_accounts)} 个新账户")
                else:
                    raise AccountManagerError("保存账户失败")
            
            result['failed'] = result['total'] - result['success'] - result['duplicated']
            
        except Exception as e:
            result['errors'].append(str(e))
            logger.error(f"导入账户失败: {e}")
        
        return result
    
    def add_account(self, account: Account) -> bool:
        """
        添加单个账户
        
        Args:
            account: 账户对象
            
        Returns:
            bool: 是否添加成功
        """
        try:
            if self.storage.add_account(account):
                self._invalidate_cache()
                logger.info(f"成功添加账户: {account.username}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"添加账户失败: {e}")
            return False
    
    def remove_account(self, username: str) -> bool:
        """
        删除账户
        
        Args:
            username: 用户名
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if self.storage.remove_account(username):
                self._invalidate_cache()
                logger.info(f"成功删除账户: {username}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"删除账户失败: {e}")
            return False
    
    def update_account(self, account: Account) -> bool:
        """
        更新账户信息
        
        Args:
            account: 账户对象
            
        Returns:
            bool: 是否更新成功
        """
        try:
            if self.storage.update_account(account):
                self._invalidate_cache()
                logger.info(f"成功更新账户: {account.username}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"更新账户失败: {e}")
            return False
    
    def get_account(self, username: str) -> Optional[Account]:
        """
        获取指定账户
        
        Args:
            username: 用户名
            
        Returns:
            Account: 账户对象，不存在则返回None
        """
        return self.storage.get_account(username)
    
    def get_all_accounts(self, refresh_cache: bool = False) -> List[Account]:
        """
        获取所有账户
        
        Args:
            refresh_cache: 是否强制刷新缓存
            
        Returns:
            List[Account]: 账户列表
        """
        self._refresh_cache(force=refresh_cache)
        return self._accounts_cache.copy()
    
    def get_active_accounts(self) -> List[Account]:
        """
        获取所有活跃账户
        
        Returns:
            List[Account]: 活跃账户列表
        """
        accounts = self.get_all_accounts()
        return [acc for acc in accounts if acc.status == AccountStatus.ACTIVE]
    
    def get_accounts_by_status(self, status: AccountStatus) -> List[Account]:
        """
        根据状态获取账户
        
        Args:
            status: 账户状态
            
        Returns:
            List[Account]: 指定状态的账户列表
        """
        accounts = self.get_all_accounts()
        return [acc for acc in accounts if acc.status == status]
    
    def update_account_status(self, username: str, status: AccountStatus) -> bool:
        """
        更新账户状态
        
        Args:
            username: 用户名
            status: 新状态
            
        Returns:
            bool: 是否更新成功
        """
        account = self.get_account(username)
        if not account:
            logger.warning(f"账户 {username} 不存在")
            return False
        
        account.update_status(status)
        return self.update_account(account)
    
    def mark_account_as_used(self, username: str) -> bool:
        """
        标记账户为已使用
        
        Args:
            username: 用户名
            
        Returns:
            bool: 是否标记成功
        """
        account = self.get_account(username)
        if not account:
            logger.warning(f"账户 {username} 不存在")
            return False
        
        account.mark_as_used()
        return self.update_account(account)
    
    def get_next_account(self, strategy: str = "round_robin", 
                        exclude_usernames: List[str] = None) -> Optional[Account]:
        """
        获取下一个可用账户（负载均衡）
        
        Args:
            strategy: 选择策略 (round_robin, random, least_used, cycle)
            exclude_usernames: 要排除的用户名列表
            
        Returns:
            Account: 下一个可用账户，无可用账户返回None
        """
        active_accounts = self.get_active_accounts()
        
        if not active_accounts:
            logger.warning("没有可用的活跃账户")
            return None
        
        # 过滤排除的账户
        if exclude_usernames:
            active_accounts = [acc for acc in active_accounts 
                             if acc.username not in exclude_usernames]
        
        if not active_accounts:
            logger.warning("所有活跃账户都被排除")
            return None
        
        # 根据策略选择账户
        if strategy == "random":
            return random.choice(active_accounts)
        
        elif strategy == "least_used":
            # 选择最少使用的账户
            def get_last_used_time(account):
                return account.last_used or datetime.min
            
            return min(active_accounts, key=get_last_used_time)
        
        elif strategy == "cycle":
            # 直接循环策略
            return self._get_next_cycle_account(active_accounts)
        
        else:  # round_robin (默认)
            # 轮询策略：选择最早使用的账户
            def get_last_used_time(account):
                return account.last_used or datetime.min
            
            return min(active_accounts, key=get_last_used_time)
    
    def _get_next_cycle_account(self, accounts: List[Account]) -> Account:
        """
        直接循环获取下一个账户
        
        Args:
            accounts: 可用账户列表
            
        Returns:
            Account: 下一个账户
        """
        # 初始化循环索引
        if not hasattr(self, '_cycle_index'):
            self._cycle_index = 0
        
        # 获取当前账户
        account = accounts[self._cycle_index]
        
        # 移动到下一个位置
        self._cycle_index = (self._cycle_index + 1) % len(accounts)
        
        # 如果回到开头，表示完成一轮循环
        if self._cycle_index == 0:
            logger.info("完成一轮账户循环，重置使用计数")
            self._reset_cycle_usage_counts(accounts)
        
        return account
    
    def _reset_cycle_usage_counts(self, accounts: List[Account]):
        """
        重置循环账户的使用计数
        
        Args:
            accounts: 要重置的账户列表
        """
        for account in accounts:
            # 如果账户有usage_count属性，重置它
            if hasattr(account, 'usage_count'):
                account.usage_count = 0
            
            # 更新最后重置时间
            account.metadata['last_cycle_reset'] = datetime.now().isoformat()
            self.update_account(account)
        
        logger.info(f"已重置 {len(accounts)} 个账户的循环计数")
    
    def validate_all_accounts(self) -> Dict[str, Any]:
        """
        验证所有账户的token有效性
        
        Returns:
            dict: 验证结果统计
        """
        accounts = self.get_all_accounts()
        
        result = {
            'total': len(accounts),
            'valid_tokens': 0,
            'invalid_tokens': 0,
            'invalid_accounts': []
        }
        
        for account in accounts:
            if account.is_token_valid():
                result['valid_tokens'] += 1
            else:
                result['invalid_tokens'] += 1
                result['invalid_accounts'].append({
                    'username': account.username,
                    'token': account.get_masked_token(),
                    'status': account.status.value
                })
        
        logger.info(f"账户验证完成: 总数={result['total']}, "
                   f"有效token={result['valid_tokens']}, "
                   f"无效token={result['invalid_tokens']}")
        
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取账户统计信息
        
        Returns:
            dict: 统计信息
        """
        accounts = self.get_all_accounts()
        
        # 状态统计
        from collections import Counter
        status_count = Counter([acc.status.value for acc in accounts])
        
        # 使用情况统计
        now = datetime.now()
        recent_used = sum(1 for acc in accounts 
                         if acc.last_used and (now - acc.last_used).days <= 1)
        
        never_used = sum(1 for acc in accounts if acc.last_used is None)
        
        # 存储统计
        storage_stats = {}
        if hasattr(self.storage, 'get_stats'):
            storage_stats = self.storage.get_stats()
        
        return {
            'total_accounts': len(accounts),
            'status_distribution': dict(status_count),
            'usage_stats': {
                'recent_used_24h': recent_used,
                'never_used': never_used,
                'cache_size': len(self._accounts_cache),
                'cache_updated_at': self._cache_updated_at.isoformat() if self._cache_updated_at else None
            },
            'storage_stats': storage_stats
        }
    
    def cleanup_inactive_accounts(self, days_threshold: int = 30) -> int:
        """
        清理长期未使用的账户
        
        Args:
            days_threshold: 天数阈值，超过此天数未使用的账户将被标记为inactive
            
        Returns:
            int: 清理的账户数量
        """
        accounts = self.get_all_accounts()
        now = datetime.now()
        threshold = timedelta(days=days_threshold)
        
        cleaned_count = 0
        
        for account in accounts:
            if (account.status == AccountStatus.ACTIVE and 
                account.last_used and 
                (now - account.last_used) > threshold):
                
                account.update_status(AccountStatus.INACTIVE)
                if self.update_account(account):
                    cleaned_count += 1
                    logger.info(f"账户 {account.username} 标记为inactive（{(now - account.last_used).days}天未使用）")
        
        return cleaned_count
    
    def export_accounts(self, include_tokens: bool = False) -> List[Dict[str, Any]]:
        """
        导出账户信息
        
        Args:
            include_tokens: 是否包含token信息
            
        Returns:
            List[dict]: 账户信息列表
        """
        accounts = self.get_all_accounts()
        
        exported = []
        for account in accounts:
            data = account.to_dict()
            
            if not include_tokens:
                # 移除敏感信息
                sensitive_fields = ['password', 'email_password', 'tfa_secret', 'auth_token']
                for field in sensitive_fields:
                    if field in data:
                        data[field] = "***HIDDEN***"
            
            exported.append(data)
        
        return exported