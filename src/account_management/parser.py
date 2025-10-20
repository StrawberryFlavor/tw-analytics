"""
账户解析器

遵循单一职责原则，只负责解析账户字符串格式
"""

import logging
from typing import List, Dict, Any, Optional
from .models import Account, AccountStatus

logger = logging.getLogger(__name__)


class AccountParseError(Exception):
    """账户解析异常"""
    pass


class AccountParser:
    """
    账户字符串解析器
    
    支持格式: username:password:email:email_password:phone_suffix:2fa_secret:auth_token
    """
    
    # 预期的字段数量
    EXPECTED_FIELDS = 7
    
    # 字段名称映射
    FIELD_NAMES = [
        'username',
        'password', 
        'email',
        'email_password',
        'phone_suffix',
        'tfa_secret',
        'auth_token'
    ]
    
    @classmethod
    def parse_account_string(cls, account_string: str) -> Account:
        """
        解析单个账户字符串
        
        Args:
            account_string: 账户字符串，格式为 username:password:email:email_password:phone_suffix:2fa_secret:auth_token
            
        Returns:
            Account: 解析后的账户对象
            
        Raises:
            AccountParseError: 解析失败时抛出
        """
        if not account_string or not account_string.strip():
            raise AccountParseError("账户字符串不能为空")
        
        # 去除首尾空白字符
        account_string = account_string.strip()
        
        # 按冒号分割
        parts = account_string.split(':')
        
        if len(parts) != cls.EXPECTED_FIELDS:
            raise AccountParseError(
                f"账户字符串格式错误，期望{cls.EXPECTED_FIELDS}个字段，实际{len(parts)}个字段"
            )
        
        # 创建字段字典
        field_dict = {}
        for i, field_name in enumerate(cls.FIELD_NAMES):
            field_value = parts[i].strip()
            if not field_value:
                raise AccountParseError(f"字段 {field_name} 不能为空")
            field_dict[field_name] = field_value
        
        try:
            # 创建账户对象
            account = Account(**field_dict)
            logger.info(f"成功解析账户: {account.username}")
            return account
            
        except Exception as e:
            raise AccountParseError(f"创建账户对象失败: {e}")
    
    @classmethod
    def parse_batch_accounts(cls, account_strings: List[str], skip_errors: bool = True) -> List[Account]:
        """
        批量解析账户字符串
        
        Args:
            account_strings: 账户字符串列表
            skip_errors: 是否跳过解析错误的账户
            
        Returns:
            List[Account]: 解析成功的账户列表
            
        Raises:
            AccountParseError: 当skip_errors=False且解析失败时抛出
        """
        accounts = []
        failed_accounts = []
        
        for i, account_string in enumerate(account_strings):
            try:
                account = cls.parse_account_string(account_string)
                accounts.append(account)
                
            except AccountParseError as e:
                error_info = {
                    'index': i,
                    'account_string': account_string[:50] + "..." if len(account_string) > 50 else account_string,
                    'error': str(e)
                }
                failed_accounts.append(error_info)
                
                if skip_errors:
                    logger.warning(f"跳过解析失败的账户 #{i}: {e}")
                else:
                    raise AccountParseError(f"解析第{i+1}个账户失败: {e}")
        
        # 记录统计信息
        total_count = len(account_strings)
        success_count = len(accounts)
        failed_count = len(failed_accounts)
        
        logger.info(f"批量解析完成: 总数={total_count}, 成功={success_count}, 失败={failed_count}")
        
        if failed_accounts:
            logger.warning(f"失败的账户详情: {failed_accounts}")
        
        return accounts
    
    @classmethod
    def parse_from_text(cls, text: str, skip_errors: bool = True) -> List[Account]:
        """
        从文本解析账户（支持多行）
        
        Args:
            text: 包含账户信息的文本，每行一个账户
            skip_errors: 是否跳过解析错误的行
            
        Returns:
            List[Account]: 解析成功的账户列表
        """
        if not text or not text.strip():
            return []
        
        # 按行分割并过滤空行
        lines = [line.strip() for line in text.strip().split('\n')]
        lines = [line for line in lines if line and not line.startswith('#')]  # 支持#注释
        
        if not lines:
            logger.warning("没有找到有效的账户行")
            return []
        
        logger.info(f"从文本中找到 {len(lines)} 行账户信息")
        return cls.parse_batch_accounts(lines, skip_errors=skip_errors)
    
    @classmethod
    def validate_account_format(cls, account_string: str) -> Dict[str, Any]:
        """
        验证账户字符串格式（不创建对象）
        
        Args:
            account_string: 账户字符串
            
        Returns:
            dict: 验证结果，包含is_valid, errors, field_count等信息
        """
        result = {
            'is_valid': False,
            'errors': [],
            'field_count': 0,
            'fields': {}
        }
        
        if not account_string or not account_string.strip():
            result['errors'].append("账户字符串为空")
            return result
        
        # 分割字段
        parts = account_string.strip().split(':')
        result['field_count'] = len(parts)
        
        if len(parts) != cls.EXPECTED_FIELDS:
            result['errors'].append(f"字段数量错误，期望{cls.EXPECTED_FIELDS}个，实际{len(parts)}个")
            return result
        
        # 验证每个字段
        for i, field_name in enumerate(cls.FIELD_NAMES):
            field_value = parts[i].strip()
            result['fields'][field_name] = field_value
            
            if not field_value:
                result['errors'].append(f"字段 {field_name} 为空")
            elif field_name == 'email' and '@' not in field_value:
                result['errors'].append(f"邮箱格式无效: {field_value}")
            elif field_name == 'auth_token' and len(field_value) < 20:
                result['errors'].append(f"auth_token长度不足: {len(field_value)}")
        
        # 设置验证结果
        result['is_valid'] = len(result['errors']) == 0
        
        return result
    
    @classmethod
    def get_sample_format(cls) -> str:
        """
        获取账户字符串格式示例
        
        Returns:
            str: 格式示例
        """
        return "username:password:email:email_password:phone_suffix:2fa_secret:auth_token"
    
    @classmethod
    def get_field_descriptions(cls) -> Dict[str, str]:
        """
        获取各字段的描述信息
        
        Returns:
            dict: 字段描述字典
        """
        return {
            'username': 'Twitter用户名',
            'password': 'Twitter密码',
            'email': '绑定邮箱',
            'email_password': '邮箱密码',
            'phone_suffix': '手机号后缀',
            'tfa_secret': '两步验证密钥',
            'auth_token': 'Twitter认证token'
        }