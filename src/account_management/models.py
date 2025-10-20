"""
账户数据模型

遵循单一职责原则，只负责账户数据的定义和基本验证
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib


class AccountStatus(Enum):
    """账户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    TOKEN_EXPIRED = "token_expired"
    UNKNOWN = "unknown"


@dataclass
class Account:
    """
    Twitter账户数据模型
    
    格式: username:password:email:email_password:phone_suffix:2fa_secret:auth_token
    """
    username: str
    password: str
    email: str
    email_password: str
    phone_suffix: str
    tfa_secret: str
    auth_token: str
    
    # 可选字段
    status: AccountStatus = field(default=AccountStatus.UNKNOWN)
    last_used: Optional[datetime] = field(default=None)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后的验证"""
        self.validate()
    
    def validate(self) -> bool:
        """
        验证账户数据完整性
        
        Returns:
            bool: 验证是否通过
            
        Raises:
            ValueError: 验证失败时抛出异常
        """
        if not self.username or not self.username.strip():
            raise ValueError("用户名不能为空")
        
        if not self.auth_token or len(self.auth_token) < 20:
            raise ValueError("auth_token无效")
        
        if not self.email or '@' not in self.email:
            raise ValueError("邮箱格式无效")
            
        return True
    
    def get_masked_token(self) -> str:
        """
        获取掩码后的token（用于日志显示）
        
        Returns:
            str: 掩码后的token
        """
        if len(self.auth_token) <= 20:
            return self.auth_token[:10] + "..."
        return self.auth_token[:20] + "..."
    
    def get_account_id(self) -> str:
        """
        生成账户唯一标识
        
        Returns:
            str: 账户ID（基于用户名的hash）
        """
        return hashlib.md5(self.username.lower().encode()).hexdigest()[:12]
    
    def is_token_valid(self) -> bool:
        """
        检查token是否看起来有效
        
        Returns:
            bool: token是否有效
        """
        return (
            self.auth_token and 
            len(self.auth_token) >= 32 and 
            all(c.isalnum() for c in self.auth_token)
        )
    
    def mark_as_used(self):
        """标记账户为已使用"""
        self.last_used = datetime.now()
        self.updated_at = datetime.now()
    
    def update_status(self, status: AccountStatus):
        """
        更新账户状态
        
        Args:
            status: 新的账户状态
        """
        self.status = status
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式（用于序列化）
        
        Returns:
            dict: 账户信息字典
        """
        return {
            'username': self.username,
            'password': self.password,
            'email': self.email,
            'email_password': self.email_password,
            'phone_suffix': self.phone_suffix,
            'tfa_secret': self.tfa_secret,
            'auth_token': self.auth_token,
            'status': self.status.value,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Account':
        """
        从字典创建账户对象
        
        Args:
            data: 账户信息字典
            
        Returns:
            Account: 账户对象
        """
        # 处理时间字段
        last_used = None
        if data.get('last_used'):
            last_used = datetime.fromisoformat(data['last_used'])
        
        created_at = datetime.now()
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        updated_at = datetime.now()
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        # 处理状态
        status = AccountStatus.UNKNOWN
        if data.get('status'):
            status = AccountStatus(data['status'])
        
        return cls(
            username=data['username'],
            password=data['password'],
            email=data['email'],
            email_password=data['email_password'],
            phone_suffix=data['phone_suffix'],
            tfa_secret=data['tfa_secret'],
            auth_token=data['auth_token'],
            status=status,
            last_used=last_used,
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get('metadata', {})
        )
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"Account({self.username}, {self.status.value}, token={self.get_masked_token()})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()