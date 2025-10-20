"""
账户切换器

遵循单一职责原则，专门负责浏览器账户切换功能
"""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from playwright.async_api import BrowserContext, Page

from .models import Account, AccountStatus
from .manager import AccountManager

logger = logging.getLogger(__name__)


class AccountSwitchError(Exception):
    """账户切换异常"""
    pass


class AccountSwitcher:
    """
    账户切换器
    
    负责在浏览器中快速切换Twitter账户
    """
    
    def __init__(self, account_manager: AccountManager = None):
        """
        初始化账户切换器
        
        Args:
            account_manager: 账户管理器实例
        """
        self.account_manager = account_manager or AccountManager()
        self.current_account: Optional[Account] = None
        self.switch_history: List[Dict[str, Any]] = []
        
        # 代理配置（从环境变量读取）
        self.proxy_config = self._get_proxy_config()
        
        logger.info("账户切换器初始化完成")
    
    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
        """获取代理配置"""
        https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
        http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
        
        if https_proxy or http_proxy:
            proxy_server = https_proxy or http_proxy
            logger.info(f"使用代理: {proxy_server}")
            return {'server': proxy_server}
        
        return None
    
    async def switch_to_account(self, context: BrowserContext, 
                               username: str, 
                               verify_login: bool = True) -> Dict[str, Any]:
        """
        切换到指定账户
        
        Args:
            context: Playwright浏览器上下文
            username: 目标用户名
            verify_login: 是否验证登录状态
            
        Returns:
            dict: 切换结果
        """
        result = {
            'success': False,
            'username': username,
            'switch_time': datetime.now().isoformat(),
            'previous_account': self.current_account.username if self.current_account else None,
            'error_message': None,
            'login_verified': False
        }
        
        try:
            # 获取目标账户
            account = self.account_manager.get_account(username)
            if not account:
                raise AccountSwitchError(f"账户 {username} 不存在")
            
            if account.status != AccountStatus.ACTIVE:
                raise AccountSwitchError(f"账户 {username} 状态为 {account.status.value}，无法切换")
            
            logger.info(f"开始切换到账户: {username}")
            
            # 清除现有cookies
            await context.clear_cookies()
            
            # 设置新的auth_token cookie
            await self._set_auth_token(context, account.auth_token)
            
            # 验证登录状态（可选）
            if verify_login:
                login_success = await self._verify_login(context, account)
                result['login_verified'] = login_success
                
                if not login_success:
                    # 更新账户状态
                    account.update_status(AccountStatus.TOKEN_EXPIRED)
                    self.account_manager.update_account(account)
                    raise AccountSwitchError(f"账户 {username} token已失效")
            
            # 更新当前账户
            self.current_account = account
            
            # 标记账户为已使用
            self.account_manager.mark_account_as_used(username)
            
            # 记录切换历史
            self._record_switch_history(result)
            
            result['success'] = True
            logger.info(f"成功切换到账户: {username}")
            
        except Exception as e:
            result['error_message'] = str(e)
            logger.error(f"切换账户失败: {e}")
        
        return result
    
    async def _set_auth_token(self, context: BrowserContext, auth_token: str) -> None:
        """
        设置auth_token cookie
        
        Args:
            context: 浏览器上下文
            auth_token: 认证token
        """
        cookies_to_set = [
            {
                'name': 'auth_token',
                'value': auth_token,
                'domain': '.twitter.com',
                'path': '/',
                'secure': True,
                'httpOnly': True,
                'sameSite': 'None'
            },
            {
                'name': 'auth_token',
                'value': auth_token,
                'domain': '.x.com',
                'path': '/',
                'secure': True,
                'httpOnly': True,
                'sameSite': 'None'
            }
        ]
        
        await context.add_cookies(cookies_to_set)
        logger.debug("auth_token cookies已设置")
    
    async def _verify_login(self, context: BrowserContext, account: Account, 
                           timeout: int = 10) -> bool:
        """
        验证登录状态
        
        Args:
            context: 浏览器上下文
            account: 账户对象
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否登录成功
        """
        try:
            page = await context.new_page()
            
            # 访问home页面
            await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=timeout*1000)
            await asyncio.sleep(2)
            
            # 检查URL是否包含home（表示登录成功）
            current_url = page.url
            if '/home' in current_url and 'login' not in current_url.lower():
                logger.debug(f"登录验证成功: {current_url}")
                await page.close()
                return True
            
            # 尝试检测登录元素
            try:
                await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"]', timeout=3000)
                logger.debug("检测到用户头像，登录成功")
                await page.close()
                return True
            except:
                pass
            
            # 检查是否能访问个人主页
            await page.goto(f'https://x.com/{account.username}', wait_until='domcontentloaded', timeout=timeout*1000)
            await asyncio.sleep(1)
            
            profile_url = page.url
            if account.username.lower() in profile_url.lower() and 'login' not in profile_url.lower():
                logger.debug(f"可以访问个人主页，登录成功: {profile_url}")
                await page.close()
                return True
            
            await page.close()
            return False
            
        except Exception as e:
            logger.warning(f"登录验证失败: {e}")
            return False
    
    def _record_switch_history(self, switch_result: Dict[str, Any]) -> None:
        """记录切换历史"""
        self.switch_history.append(switch_result.copy())
        
        # 只保留最近100条记录
        if len(self.switch_history) > 100:
            self.switch_history = self.switch_history[-100:]
    
    async def auto_switch_account(self, context: BrowserContext, 
                                 strategy: str = "round_robin",
                                 exclude_current: bool = True) -> Dict[str, Any]:
        """
        自动切换到下一个可用账户
        
        Args:
            context: 浏览器上下文
            strategy: 选择策略
            exclude_current: 是否排除当前账户
            
        Returns:
            dict: 切换结果
        """
        exclude_usernames = []
        if exclude_current and self.current_account:
            exclude_usernames.append(self.current_account.username)
        
        # 获取下一个账户
        next_account = self.account_manager.get_next_account(
            strategy=strategy, 
            exclude_usernames=exclude_usernames
        )
        
        if not next_account:
            return {
                'success': False,
                'error_message': '没有可用的账户进行切换',
                'switch_time': datetime.now().isoformat()
            }
        
        return await self.switch_to_account(context, next_account.username)
    
    async def batch_switch_test(self, context: BrowserContext, 
                               usernames: List[str] = None, 
                               max_accounts: int = 5) -> Dict[str, Any]:
        """
        批量测试账户切换
        
        Args:
            context: 浏览器上下文
            usernames: 要测试的用户名列表，None则测试所有活跃账户
            max_accounts: 最大测试账户数
            
        Returns:
            dict: 测试结果
        """
        if usernames is None:
            active_accounts = self.account_manager.get_active_accounts()
            usernames = [acc.username for acc in active_accounts[:max_accounts]]
        
        results = {
            'total_tested': len(usernames),
            'successful_switches': 0,
            'failed_switches': 0,
            'test_results': [],
            'start_time': datetime.now().isoformat()
        }
        
        for username in usernames:
            logger.info(f"测试切换到账户: {username}")
            
            switch_result = await self.switch_to_account(context, username, verify_login=True)
            results['test_results'].append(switch_result)
            
            if switch_result['success']:
                results['successful_switches'] += 1
            else:
                results['failed_switches'] += 1
            
            # 短暂延迟避免频繁请求
            await asyncio.sleep(2)
        
        results['end_time'] = datetime.now().isoformat()
        logger.info(f"批量切换测试完成: 成功={results['successful_switches']}, 失败={results['failed_switches']}")
        
        return results
    
    def get_current_account(self) -> Optional[Account]:
        """
        获取当前账户
        
        Returns:
            Account: 当前账户，无则返回None
        """
        return self.current_account
    
    def get_switch_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取切换历史
        
        Args:
            limit: 返回记录数限制
            
        Returns:
            List[dict]: 切换历史记录
        """
        return self.switch_history[-limit:] if self.switch_history else []
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取切换统计信息
        
        Returns:
            dict: 统计信息
        """
        if not self.switch_history:
            return {
                'total_switches': 0,
                'successful_switches': 0,
                'failed_switches': 0,
                'success_rate': 0.0,
                'current_account': None
            }
        
        total = len(self.switch_history)
        successful = sum(1 for record in self.switch_history if record['success'])
        failed = total - successful
        success_rate = (successful / total) * 100 if total > 0 else 0
        
        return {
            'total_switches': total,
            'successful_switches': successful,
            'failed_switches': failed,
            'success_rate': round(success_rate, 2),
            'current_account': self.current_account.username if self.current_account else None,
            'last_switch_time': self.switch_history[-1]['switch_time'] if self.switch_history else None
        }
    
    async def emergency_switch(self, context: BrowserContext) -> Dict[str, Any]:
        """
        紧急切换账户（当检测到限制时使用）
        
        Args:
            context: 浏览器上下文
            
        Returns:
            dict: 切换结果
        """
        logger.warning("执行紧急账户切换")
        
        # 标记当前账户可能有问题
        if self.current_account:
            self.current_account.update_status(AccountStatus.INACTIVE)
            self.account_manager.update_account(self.current_account)
        
        # 尝试切换到随机账户
        return await self.auto_switch_account(context, strategy="random", exclude_current=True)