"""
账户存储接口和实现

遵循接口隔离和依赖倒置原则
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import Account

logger = logging.getLogger(__name__)

try:
    from filelock import FileLock
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False
    logger.warning("filelock not installed, file locking disabled")


class IAccountStorage(ABC):
    """账户存储接口"""
    
    @abstractmethod
    def save_accounts(self, accounts: List[Account]) -> bool:
        """保存账户列表"""
        pass
    
    @abstractmethod
    def load_accounts(self) -> List[Account]:
        """加载账户列表"""
        pass
    
    @abstractmethod
    def add_account(self, account: Account) -> bool:
        """添加单个账户"""
        pass
    
    @abstractmethod
    def remove_account(self, username: str) -> bool:
        """删除账户"""
        pass
    
    @abstractmethod
    def update_account(self, account: Account) -> bool:
        """更新账户信息"""
        pass
    
    @abstractmethod
    def get_account(self, username: str) -> Optional[Account]:
        """获取指定账户"""
        pass
    
    @abstractmethod
    def account_exists(self, username: str) -> bool:
        """检查账户是否存在"""
        pass


class JsonAccountStorage(IAccountStorage):
    """
    JSON文件存储实现
    
    遵循KISS原则，使用简单的JSON文件存储
    """
    
    def __init__(self, file_path: str = None):
        """
        初始化JSON存储
        
        Args:
            file_path: JSON文件路径，默认从配置获取
        """
        if file_path is None:
            # 从配置获取存储路径
            import os
            config_path = os.getenv('ACCOUNT_CONFIG_PATH', 'src/config/accounts.json')
            if not os.path.isabs(config_path):
                # 相对路径，基于项目根目录
                project_root = Path(__file__).parent.parent.parent
                file_path = project_root / config_path
            else:
                file_path = Path(config_path)
        
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化文件锁（仅用于写操作）
        if FILELOCK_AVAILABLE:
            lock_file = self.file_path.with_suffix('.lock')
            self.write_lock = FileLock(str(lock_file), timeout=10)
        else:
            self.write_lock = None
        
        # 内存缓存 - 遵循KISS原则的简单缓存实现
        self._cache = None
        self._cache_timestamp = 0
        self._cache_ttl = 30  # 30秒缓存时间
        
        logger.info(f"账户存储文件: {self.file_path}, 写锁: {'启用' if self.write_lock else '禁用'}, 缓存TTL: {self._cache_ttl}s")
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        import time
        return (self._cache is not None and 
                time.time() - self._cache_timestamp < self._cache_ttl)
    
    def _update_cache(self, data: Dict[str, Any]) -> None:
        """更新缓存"""
        import time
        self._cache = data.copy()
        self._cache_timestamp = time.time()
    
    def _invalidate_cache(self) -> None:
        """清除缓存"""
        self._cache = None
        self._cache_timestamp = 0
    
    def _load_data_from_file(self) -> Dict[str, Any]:
        """从文件加载数据（无锁读取）"""
        if not self.file_path.exists():
            return {'accounts': [], 'metadata': {'version': '1.0'}}
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据结构正确
                if 'accounts' not in data:
                    data['accounts'] = []
                if 'metadata' not in data:
                    data['metadata'] = {'version': '1.0'}
                return data
        except Exception as e:
            logger.error(f"加载账户数据失败: {e}")
            return {'accounts': [], 'metadata': {'version': '1.0'}}
    
    def _load_data(self) -> Dict[str, Any]:
        """加载JSON数据（优先使用缓存，读操作不加锁）"""
        # 优先从缓存读取
        if self._is_cache_valid():
            logger.debug("从缓存加载账户数据")
            return self._cache.copy()
        
        # 缓存失效，从文件读取（读操作不加锁，提升并发性能）
        logger.debug("从文件加载账户数据")
        data = self._load_data_from_file()
        
        # 更新缓存
        self._update_cache(data)
        
        return data
    
    def _save_data(self, data: Dict[str, Any]) -> bool:
        """保存JSON数据（带文件锁）"""
        def _do_save():
            try:
                # 创建备份
                if self.file_path.exists():
                    backup_path = self.file_path.with_suffix('.json.bak')
                    import shutil
                    shutil.copy2(self.file_path, backup_path)
                
                # 保存新数据
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                return True
                
            except Exception as e:
                logger.error(f"保存账户数据失败: {e}")
                # 尝试恢复备份
                backup_path = self.file_path.with_suffix('.json.bak')
                if backup_path.exists():
                    import shutil
                    shutil.copy2(backup_path, self.file_path)
                return False
        
        # 使用写锁（只有写操作才加锁）
        if self.write_lock:
            with self.write_lock:
                result = _do_save()
                if result:
                    # 写入成功后，清除缓存以确保数据一致性
                    self._invalidate_cache()
                return result
        else:
            result = _do_save()
            if result:
                self._invalidate_cache()
            return result
    
    def save_accounts(self, accounts: List[Account]) -> bool:
        """保存账户列表"""
        try:
            data = self._load_data()
            data['accounts'] = [account.to_dict() for account in accounts]
            data['metadata']['last_updated'] = datetime.now().isoformat()
            data['metadata']['total_accounts'] = len(accounts)
            
            success = self._save_data(data)
            if success:
                logger.info(f"成功保存 {len(accounts)} 个账户")
            return success
            
        except Exception as e:
            logger.error(f"保存账户失败: {e}")
            return False
    
    def batch_update_accounts(self, updates: List[Dict[str, Any]]) -> bool:
        """
        批量更新账户 - 提升性能的关键优化
        
        Args:
            updates: 更新列表，每个元素包含 {'username': str, 'updates': dict}
        
        Returns:
            bool: 更新是否成功
        """
        if not updates:
            return True
            
        try:
            # 使用写锁保护整个批量操作
            def _do_batch_update():
                data = self._load_data_from_file()  # 直接从文件读取最新数据
                
                # 创建账户索引以提高查找效率
                account_index = {acc_data['username']: i 
                               for i, acc_data in enumerate(data['accounts'])}
                
                updated_count = 0
                for update_item in updates:
                    username = update_item['username']
                    update_data = update_item['updates']
                    
                    if username in account_index:
                        idx = account_index[username]
                        data['accounts'][idx].update(update_data)
                        updated_count += 1
                
                # 更新元数据
                data['metadata']['last_updated'] = datetime.now().isoformat()
                data['metadata']['batch_update_count'] = updated_count
                
                return self._save_data_internal(data), updated_count
            
            if self.write_lock:
                with self.write_lock:
                    success, count = _do_batch_update()
                    if success:
                        self._invalidate_cache()
                        logger.info(f"批量更新 {count} 个账户成功")
                    return success
            else:
                success, count = _do_batch_update()
                if success:
                    self._invalidate_cache()
                    logger.info(f"批量更新 {count} 个账户成功")
                return success
                
        except Exception as e:
            logger.error(f"批量更新账户失败: {e}")
            return False
    
    def _save_data_internal(self, data: Dict[str, Any]) -> bool:
        """内部保存方法，不处理锁和缓存"""
        try:
            # 创建备份
            if self.file_path.exists():
                backup_path = self.file_path.with_suffix('.json.bak')
                import shutil
                shutil.copy2(self.file_path, backup_path)
            
            # 保存新数据
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"保存账户数据失败: {e}")
            # 尝试恢复备份
            backup_path = self.file_path.with_suffix('.json.bak')
            if backup_path.exists():
                import shutil
                shutil.copy2(backup_path, self.file_path)
            return False

    def load_accounts(self) -> List[Account]:
        """加载账户列表（优化版本）"""
        try:
            data = self._load_data()  # 使用缓存优化的加载
            accounts = []
            
            for account_data in data['accounts']:
                try:
                    account = Account.from_dict(account_data)
                    accounts.append(account)
                except Exception as e:
                    logger.warning(f"跳过无效账户数据: {e}")
                    continue
            
            logger.info(f"成功加载 {len(accounts)} 个账户")
            return accounts
            
        except Exception as e:
            logger.error(f"加载账户失败: {e}")
            return []
    
    def add_account(self, account: Account) -> bool:
        """添加单个账户"""
        try:
            accounts = self.load_accounts()
            
            # 检查是否已存在
            if any(acc.username == account.username for acc in accounts):
                logger.warning(f"账户 {account.username} 已存在")
                return False
            
            accounts.append(account)
            return self.save_accounts(accounts)
            
        except Exception as e:
            logger.error(f"添加账户失败: {e}")
            return False
    
    def remove_account(self, username: str) -> bool:
        """删除账户"""
        try:
            accounts = self.load_accounts()
            original_count = len(accounts)
            
            accounts = [acc for acc in accounts if acc.username != username]
            
            if len(accounts) == original_count:
                logger.warning(f"账户 {username} 不存在")
                return False
            
            success = self.save_accounts(accounts)
            if success:
                logger.info(f"成功删除账户 {username}")
            return success
            
        except Exception as e:
            logger.error(f"删除账户失败: {e}")
            return False
    
    def update_account(self, account: Account) -> bool:
        """更新账户信息"""
        try:
            accounts = self.load_accounts()
            
            for i, acc in enumerate(accounts):
                if acc.username == account.username:
                    accounts[i] = account
                    success = self.save_accounts(accounts)
                    if success:
                        logger.info(f"成功更新账户 {account.username}")
                    return success
            
            logger.warning(f"账户 {account.username} 不存在，无法更新")
            return False
            
        except Exception as e:
            logger.error(f"更新账户失败: {e}")
            return False
    
    def get_account(self, username: str) -> Optional[Account]:
        """获取指定账户"""
        try:
            accounts = self.load_accounts()
            
            for account in accounts:
                if account.username == username:
                    return account
            
            return None
            
        except Exception as e:
            logger.error(f"获取账户失败: {e}")
            return None
    
    def account_exists(self, username: str) -> bool:
        """检查账户是否存在"""
        return self.get_account(username) is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            data = self._load_data()
            accounts = self.load_accounts()
            
            from collections import Counter
            status_count = Counter([acc.status.value for acc in accounts])
            
            return {
                'total_accounts': len(accounts),
                'file_size_bytes': self.file_path.stat().st_size if self.file_path.exists() else 0,
                'status_distribution': dict(status_count),
                'last_updated': data['metadata'].get('last_updated'),
                'version': data['metadata'].get('version')
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}


class MemoryAccountStorage(IAccountStorage):
    """
    内存存储实现（用于测试）
    """
    
    def __init__(self):
        self._accounts: Dict[str, Account] = {}
    
    def save_accounts(self, accounts: List[Account]) -> bool:
        self._accounts = {acc.username: acc for acc in accounts}
        return True
    
    def load_accounts(self) -> List[Account]:
        return list(self._accounts.values())
    
    def add_account(self, account: Account) -> bool:
        if account.username in self._accounts:
            return False
        self._accounts[account.username] = account
        return True
    
    def remove_account(self, username: str) -> bool:
        if username not in self._accounts:
            return False
        del self._accounts[username]
        return True
    
    def update_account(self, account: Account) -> bool:
        if account.username not in self._accounts:
            return False
        self._accounts[account.username] = account
        return True
    
    def get_account(self, username: str) -> Optional[Account]:
        return self._accounts.get(username)
    
    def account_exists(self, username: str) -> bool:
        return username in self._accounts