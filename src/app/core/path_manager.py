"""
统一的路径管理工具
提供项目路径解析和环境变量加载的统一接口
"""

import os
from typing import Optional
from dotenv import load_dotenv


class PathManager:
    """路径管理器 - 单例模式"""
    
    _instance: Optional['PathManager'] = None
    _project_root: Optional[str] = None
    _env_loaded: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_project_root(self) -> str:
        """获取项目根目录"""
        if self._project_root is not None:
            return self._project_root
            
        # 从当前文件位置向上查找
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 向上遍历查找run.py（项目根目录标识）
        while current_dir != '/' and current_dir != os.path.dirname(current_dir):
            if os.path.exists(os.path.join(current_dir, 'run.py')):
                self._project_root = current_dir
                return current_dir
            current_dir = os.path.dirname(current_dir)
        
        # 备选方案：基于工作目录推断
        cwd = os.getcwd()
        
        # 如果当前工作目录就是项目根目录
        if os.path.exists(os.path.join(cwd, 'run.py')):
            self._project_root = cwd
            return cwd
        
        # 如果当前在src目录，父目录可能是项目根目录
        if os.path.basename(cwd) == 'src':
            parent_dir = os.path.dirname(cwd)
            if os.path.exists(os.path.join(parent_dir, 'run.py')):
                self._project_root = parent_dir
                return parent_dir
        
        # 最后的备选方案
        self._project_root = cwd
        return cwd
    
    def get_cookie_file_path(self, relative_path: str = "instance/twitter_cookies.json") -> str:
        """获取cookie文件绝对路径"""
        project_root = self.get_project_root()
        cookie_path = os.path.join(project_root, relative_path)
        
        # 调试信息（仅在DEBUG模式下）
        if os.getenv('FLASK_DEBUG', '').lower() == 'true':
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Cookie path: cwd={os.getcwd()}, root={project_root}, path={cookie_path}")
        
        return cookie_path
    
    def load_env_file(self) -> bool:
        """加载.env文件，返回是否成功加载"""
        if self._env_loaded:
            return True
            
        project_root = self.get_project_root()
        
        # 尝试多个可能的.env文件位置
        env_candidates = [
            os.path.join(project_root, '.env'),              # 项目根目录
            os.path.join(os.getcwd(), '.env'),               # 当前工作目录
            os.path.join(project_root, 'config', '.env')     # config目录
        ]
        
        # 如果在src目录，添加父目录
        if os.path.basename(os.getcwd()) == 'src':
            env_candidates.insert(1, os.path.join(os.path.dirname(os.getcwd()), '.env'))
        
        for env_path in env_candidates:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                self._env_loaded = True
                
                # 调试信息
                if os.getenv('FLASK_DEBUG', '').lower() == 'true':
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"Loaded .env from: {env_path}")
                
                return True
        
        # 没找到.env文件也标记为已尝试
        self._env_loaded = True
        return False
    
    def get_file_path(self, relative_path: str) -> str:
        """获取项目文件的绝对路径"""
        return os.path.join(self.get_project_root(), relative_path)


# 全局实例
_path_manager = PathManager()

# 便捷函数
def get_project_root() -> str:
    """获取项目根目录"""
    return _path_manager.get_project_root()

def get_cookie_file_path(relative_path: str = "instance/twitter_cookies.json") -> str:
    """获取cookie文件路径"""
    return _path_manager.get_cookie_file_path(relative_path)

def load_env_file() -> bool:
    """加载环境变量文件"""
    return _path_manager.load_env_file()

def get_file_path(relative_path: str) -> str:
    """获取项目文件路径"""
    return _path_manager.get_file_path(relative_path)