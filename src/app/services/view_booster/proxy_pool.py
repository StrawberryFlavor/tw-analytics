"""
代理池管理器
遵循单一职责原则，专门负责代理的轮换和管理
"""

import logging
import random
import threading
from pathlib import Path
from typing import List, Optional


class ProxyPool:
    """
    代理池管理器
    自动轮换使用代理列表
    """
    
    def __init__(self, proxies_file: str = "scripts/proxies.txt", enabled: bool = True):
        """
        初始化代理池
        
        Args:
            proxies_file: 代理文件路径
            enabled: 是否启用代理池
        """
        self.enabled = enabled
        self.proxies_file = proxies_file
        self.proxies: List[str] = []
        self.current_index = 0
        self.lock = threading.Lock()
        self.logger = self._setup_logger()
        
        if self.enabled:
            self.load_proxies()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(f"{__name__}.{id(self)}")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def load_proxies(self) -> bool:
        """
        从文件加载代理列表
        
        Returns:
            bool: 是否加载成功
        """
        try:
            # 确定代理文件路径
            if not Path(self.proxies_file).is_absolute():
                # 相对于项目根目录
                project_root = Path(__file__).parent.parent.parent.parent.parent
                proxy_path = project_root / self.proxies_file
            else:
                proxy_path = Path(self.proxies_file)
            
            if not proxy_path.exists():
                self.logger.warning(f"代理文件不存在: {proxy_path}")
                self.enabled = False
                return False
            
            with open(proxy_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 解析代理
            self.proxies = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    # 验证代理格式
                    if self._validate_proxy(line):
                        self.proxies.append(line)
                    else:
                        self.logger.warning(f"代理格式无效 (行{line_num}): {line[:50]}...")
            
            if self.proxies:
                self.logger.info(f"成功加载 {len(self.proxies)} 个代理")
                # 随机打乱代理顺序
                random.shuffle(self.proxies)
                return True
            else:
                self.logger.warning("没有找到有效的代理")
                self.enabled = False
                return False
                
        except Exception as e:
            self.logger.error(f"加载代理文件失败: {e}")
            self.enabled = False
            return False
    
    def _validate_proxy(self, proxy: str) -> bool:
        """
        验证代理格式
        
        Args:
            proxy: 代理字符串 (格式: HOST:PORT:USER:PASS)
            
        Returns:
            bool: 是否有效
        """
        try:
            # 支持 HOST:PORT:USER:PASS 格式
            parts = proxy.strip().split(':')
            if len(parts) == 4:
                host, port, user, password = parts
                # 验证端口是数字
                int(port)
                # 验证必要字段不为空
                return all([host, port, user, password])
            return False
                
        except Exception:
            return False
    
    def get_next_proxy(self) -> Optional[str]:
        """
        获取下一个代理
        
        Returns:
            str: 代理URL，无可用代理返回None
        """
        if not self.enabled or not self.proxies:
            return None
        
        with self.lock:
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            self.logger.debug(f"分配代理 {self.current_index}/{len(self.proxies)}: {proxy[:30]}...")
            return proxy
    
    def get_random_proxy(self) -> Optional[str]:
        """
        获取随机代理
        
        Returns:
            str: 代理URL，无可用代理返回None
        """
        if not self.enabled or not self.proxies:
            return None
        
        proxy = random.choice(self.proxies)
        self.logger.debug(f"随机分配代理: {proxy[:30]}...")
        return proxy
    
    def get_proxy_for_instance(self, instance_id: int) -> Optional[str]:
        """
        为特定实例获取代理（确保同一实例使用相同代理）
        
        Args:
            instance_id: 实例ID
            
        Returns:
            str: 代理URL，无可用代理返回None
        """
        if not self.enabled or not self.proxies:
            return None
        
        # 根据实例ID确定代理索引，确保同一实例总是使用相同代理
        proxy_index = instance_id % len(self.proxies)
        proxy = self.proxies[proxy_index]
        
        self.logger.debug(f"实例 {instance_id} 分配代理: {proxy[:30]}...")
        return proxy
    
    def is_enabled(self) -> bool:
        """检查代理池是否已启用"""
        return self.enabled and len(self.proxies) > 0
    
    def get_stats(self) -> dict:
        """
        获取代理池统计信息
        
        Returns:
            dict: 统计信息
        """
        return {
            'enabled': self.enabled,
            'total_proxies': len(self.proxies),
            'current_index': self.current_index,
            'proxies_file': self.proxies_file,
            'has_valid_proxies': len(self.proxies) > 0
        }
    
    def reload_proxies(self) -> bool:
        """
        重新加载代理文件
        
        Returns:
            bool: 是否重新加载成功
        """
        self.logger.info("重新加载代理文件...")
        with self.lock:
            self.current_index = 0
            return self.load_proxies()
    
    def disable(self):
        """禁用代理池"""
        self.enabled = False
        self.logger.info("代理池已禁用")
    
    def enable(self) -> bool:
        """
        启用代理池
        
        Returns:
            bool: 是否启用成功
        """
        if not self.proxies:
            success = self.load_proxies()
        else:
            success = True
            self.enabled = True
        
        if success:
            self.logger.info("代理池已启用")
        
        return success
