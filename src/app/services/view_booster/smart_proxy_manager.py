"""
智能代理管理器
解决本地代理(科学上网)和代理池(业务需求)的冲突问题
"""

import os
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any
from enum import Enum

from .proxy_pool import ProxyPool


class NetworkMode(Enum):
    """网络模式"""
    AUTO = "auto"           # 自动检测
    DIRECT = "direct"       # 直连
    LOCAL_PROXY = "local_proxy"    # 本地代理(科学上网)
    PROXY_POOL = "proxy_pool"      # 代理池(业务需求)


class NetworkError(Exception):
    """网络连接错误"""
    pass


class SmartProxyManager:
    """智能代理管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 从环境变量读取配置
        self.network_mode = NetworkMode(os.getenv('NETWORK_MODE', 'auto'))
        self.local_proxy = os.getenv('LOCAL_PROXY', '127.0.0.1:7890')
        self.proxy_pool_enabled = os.getenv('PROXY_POOL_ENABLED', 'true').lower() == 'true'
        self.proxy_pool_file = os.getenv('PROXY_POOL_FILE', 'scripts/proxies.txt')
        
        # 初始化代理池
        self.proxy_pool = ProxyPool(proxies_file=self.proxy_pool_file) if self.proxy_pool_enabled else None
        
        # 缓存网络检测结果
        self._can_direct_connect = None
        self._detection_time = None
        self._cache_duration = 300  # 5分钟缓存
        
        self.logger.info(f"🔧 智能代理管理器初始化:")
        self.logger.info(f"   网络模式: {self.network_mode.value}")
        self.logger.info(f"   本地代理: {self.local_proxy if self.local_proxy else '未配置'}")
        self.logger.info(f"   代理池: {'启用' if self.proxy_pool_enabled else '禁用'}")
        if self.proxy_pool_enabled:
            self.logger.info(f"   代理池文件: {self.proxy_pool_file}")
            pool_count = len(self.proxy_pool.proxies) if self.proxy_pool else 0
            self.logger.info(f"   代理数量: {pool_count}")
    
    async def get_proxy_config(self, 
                              override_use_proxy_pool: Optional[bool] = None,
                              override_network_mode: Optional[str] = None,
                              override_proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取适合当前环境的代理配置
        
        Args:
            override_use_proxy_pool: API请求级别的代理池设置，优先级高于环境变量
            override_network_mode: API请求级别的网络模式设置，优先级高于环境变量
            override_proxy: API请求级别的单一代理设置，最高优先级
        """
        
        # 最高优先级：单一代理参数
        if override_proxy:
            self.logger.info(f"🔄 使用API指定的单一代理: {override_proxy}")
            return self._parse_single_proxy(override_proxy)
        
        # 确定生效的网络模式（API参数优先）
        effective_network_mode = self.network_mode
        if override_network_mode:
            try:
                effective_network_mode = NetworkMode(override_network_mode)
                self.logger.info(f"🔄 使用API覆盖的网络模式: {override_network_mode}")
            except ValueError:
                self.logger.warning(f"⚠️ 无效的网络模式覆盖参数: {override_network_mode}，使用环境变量设置")
        
        # 确定生效的代理池设置（API参数优先）
        effective_proxy_pool_enabled = self.proxy_pool_enabled
        if override_use_proxy_pool is not None:
            effective_proxy_pool_enabled = override_use_proxy_pool
            self.logger.info(f"🔄 使用API覆盖的代理池设置: {override_use_proxy_pool}")
        
        if effective_network_mode == NetworkMode.AUTO:
            return await self._auto_detect_proxy(effective_proxy_pool_enabled)
        elif effective_network_mode == NetworkMode.DIRECT:
            self.logger.info("🌐 使用直连模式")
            return None
        elif effective_network_mode == NetworkMode.LOCAL_PROXY:
            self.logger.info("🔒 使用本地代理模式")
            return self._get_local_proxy_config()
        elif effective_network_mode == NetworkMode.PROXY_POOL:
            self.logger.info("🌍 使用代理池模式")
            return await self._get_pool_proxy_config() if effective_proxy_pool_enabled else None
        else:
            raise ValueError(f"未知的网络模式: {effective_network_mode}")
    
    async def _auto_detect_proxy(self, effective_proxy_pool_enabled: bool = None) -> Optional[Dict[str, Any]]:
        """自动检测并选择最佳代理配置"""
        
        if effective_proxy_pool_enabled is None:
            effective_proxy_pool_enabled = self.proxy_pool_enabled
        
        self.logger.info("🔍 自动检测网络环境...")
        
        # 检查缓存
        import time
        current_time = time.time()
        if (self._detection_time and 
            current_time - self._detection_time < self._cache_duration):
            self.logger.debug("使用缓存的网络检测结果")
        else:
            # 重新检测
            self._can_direct_connect = await self._test_direct_connection()
            self._detection_time = current_time
        
        if self._can_direct_connect:
            self.logger.info("✅ 网络可直连x.com")
            if effective_proxy_pool_enabled:
                self.logger.info("🌍 选择代理池模式 (业务需求)")
                return await self._get_pool_proxy_config()
            else:
                self.logger.info("🌐 选择直连模式")
                return None
        else:
            self.logger.info("❌ 网络无法直连x.com")
            if self.local_proxy:
                self.logger.info("🔒 选择本地代理模式 (科学上网)")
                return self._get_local_proxy_config()
            else:
                raise NetworkError(
                    "无法连接到x.com且未配置本地代理。"
                    "请设置 LOCAL_PROXY 环境变量或检查网络连接。"
                )
    
    async def _test_direct_connection(self) -> bool:
        """测试是否能直连x.com"""
        
        self.logger.debug("测试直连x.com...")
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10),
                verify=False,
                trust_env=False  # 忽略系统代理设置
            ) as client:
                response = await client.get("https://x.com")
                success = response.status_code in [200, 302, 400, 403, 429]  # 只要不是网络错误就算连通
                
                if success:
                    self.logger.debug("✅ x.com直连测试成功")
                else:
                    self.logger.debug(f"❌ x.com直连测试失败: HTTP {response.status_code}")
                
                return success
                
        except Exception as e:
            self.logger.debug(f"❌ x.com直连测试异常: {e}")
            return False
    
    def _parse_single_proxy(self, proxy_url: str) -> Optional[Dict[str, Any]]:
        """解析单一代理URL"""
        
        if not proxy_url:
            return None
        
        # 处理不同格式的代理地址
        if not proxy_url.startswith(('http://', 'https://', 'socks5://')):
            proxy_url = f"http://{proxy_url}"
        
        return {
            "http://": proxy_url,
            "https://": proxy_url
        }
    
    def _get_local_proxy_config(self) -> Optional[Dict[str, Any]]:
        """获取本地代理配置"""
        
        if not self.local_proxy:
            return None
        
        return self._parse_single_proxy(self.local_proxy)
    
    async def _get_pool_proxy_config(self) -> Optional[Dict[str, Any]]:
        """获取代理池配置"""
        
        if not self.proxy_pool:
            return None
        
        proxy = self.proxy_pool.get_proxy_for_instance(0)
        if not proxy:
            self.logger.warning("代理池没有可用的代理")
            return None
        
        # 解析代理格式: HOST:PORT:USER:PASS
        parts = proxy.strip().split(':')
        if len(parts) >= 4:
            host, port, username = parts[0], parts[1], parts[2]
            # 密码可能包含冒号，所以需要重新拼接剩余部分
            password = ':'.join(parts[3:])
            
            # SOCKS5代理格式
            proxy_url = f"socks5://{username}:{password}@{host}:{port}"
            
            self.logger.debug(f"使用代理池代理: {host}:{port}")
            
            return {
                "http://": proxy_url,
                "https://": proxy_url
            }
        else:
            self.logger.error(f"代理格式错误: {proxy}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        
        return {
            "network_mode": self.network_mode.value,
            "local_proxy": self.local_proxy,
            "proxy_pool_enabled": self.proxy_pool_enabled,
            "proxy_pool_file": self.proxy_pool_file,
            "can_direct_connect": self._can_direct_connect,
            "proxy_pool_count": len(self.proxy_pool.proxies) if self.proxy_pool else 0
        }
    
    async def test_proxy_connection(self, test_url: str = "https://x.com") -> bool:
        """测试当前代理配置是否可用"""
        
        self.logger.info(f"🔍 测试代理连接: {test_url}")
        
        try:
            proxy_config = await self.get_proxy_config()
            
            client_config = {
                "timeout": httpx.Timeout(10),
                "verify": False,
                "trust_env": False
            }
            
            if proxy_config:
                client_config["proxies"] = proxy_config
                self.logger.debug(f"使用代理配置: {list(proxy_config.keys())}")
            else:
                self.logger.debug("使用直连")
            
            async with httpx.AsyncClient(**client_config) as client:
                response = await client.get(test_url)
                # x.com 可能返回 400, 403, 200, 302 等状态码，只要不是网络错误就算连通
                success = response.status_code in [200, 302, 400, 403, 429]
                
                if success:
                    self.logger.info(f"✅ 代理连接测试成功: HTTP {response.status_code}")
                else:
                    self.logger.error(f"❌ 代理连接测试失败: HTTP {response.status_code}")
                
                return success
                
        except Exception as e:
            self.logger.error(f"❌ 代理连接测试异常: {e}")
            return False


# 单例实例
_smart_proxy_manager = None

def get_smart_proxy_manager() -> SmartProxyManager:
    """获取智能代理管理器单例"""
    global _smart_proxy_manager
    if _smart_proxy_manager is None:
        _smart_proxy_manager = SmartProxyManager()
    return _smart_proxy_manager