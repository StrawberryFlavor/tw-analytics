"""
智能截图管理器 - 用于生产环境的截图策略
"""

import os
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from dataclasses import dataclass
from enum import Enum


class ScreenshotType(Enum):
    """截图类型"""
    FIRST_LOAD = "first_load"      # 首次加载
    MILESTONE = "milestone"         # 里程碑（如每100次）
    ERROR = "error"                 # 错误时
    FINAL = "final"                 # 任务完成
    DEBUG = "debug"                 # 调试模式


@dataclass
class ScreenshotConfig:
    """截图配置"""
    enabled: bool = True                        # 是否启用截图
    debug_mode: bool = False                    # 调试模式（频繁截图）
    
    # 存储配置
    base_dir: str = "/tmp/twitter_screenshots"  # 基础目录
    max_storage_mb: int = 100                   # 最大存储空间(MB)
    retention_hours: int = 24                   # 保留时间(小时)
    
    # 截图策略
    milestone_interval: int = 100               # 里程碑间隔
    error_screenshot: bool = True               # 错误时截图
    first_screenshot: bool = True               # 首次访问截图
    final_screenshot: bool = True               # 完成时截图
    
    # 调试模式配置
    debug_interval: int = 5                     # 调试模式截图间隔
    debug_max_screenshots: int = 20             # 调试模式最大截图数


class ScreenshotManager:
    """智能截图管理器"""
    
    def __init__(self, config: Optional[ScreenshotConfig] = None):
        self.config = config or ScreenshotConfig()
        self.logger = logging.getLogger(__name__)
        self.screenshot_count = {}  # 记录每个标签页的截图次数
        self.total_screenshots = 0
        
        # 初始化存储目录
        self._init_storage()
    
    def _init_storage(self):
        """初始化存储目录"""
        if self.config.enabled:
            # 创建按日期的子目录
            date_str = datetime.now().strftime("%Y%m%d")
            self.current_dir = Path(self.config.base_dir) / date_str
            self.current_dir.mkdir(parents=True, exist_ok=True)
            
            # 清理过期目录
            self._cleanup_old_directories()
    
    def _cleanup_old_directories(self):
        """清理过期目录"""
        try:
            base_path = Path(self.config.base_dir)
            if not base_path.exists():
                return
            
            cutoff_date = datetime.now() - timedelta(hours=self.config.retention_hours)
            
            for dir_path in base_path.iterdir():
                if dir_path.is_dir():
                    # 解析目录名中的日期
                    try:
                        dir_date = datetime.strptime(dir_path.name, "%Y%m%d")
                        if dir_date < cutoff_date:
                            shutil.rmtree(dir_path)
                            self.logger.info(f"♻️ 清理过期目录: {dir_path}")
                    except ValueError:
                        # 非日期格式的目录，跳过
                        continue
                        
        except Exception as e:
            self.logger.error(f"清理目录失败: {e}")
    
    def _check_storage_limit(self) -> bool:
        """检查存储限制"""
        try:
            total_size = 0
            for root, dirs, files in os.walk(self.config.base_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
            
            size_mb = total_size / (1024 * 1024)
            
            if size_mb > self.config.max_storage_mb:
                self.logger.warning(f"⚠️ 存储空间超限: {size_mb:.1f}MB > {self.config.max_storage_mb}MB")
                # 删除最旧的文件
                self._cleanup_oldest_files()
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查存储失败: {e}")
            return True
    
    def _cleanup_oldest_files(self):
        """删除最旧的文件释放空间"""
        try:
            files = []
            for root, _, filenames in os.walk(self.config.base_dir):
                for filename in filenames:
                    if filename.endswith('.png'):
                        file_path = os.path.join(root, filename)
                        files.append((file_path, os.path.getmtime(file_path)))
            
            # 按修改时间排序
            files.sort(key=lambda x: x[1])
            
            # 删除最旧的20%文件
            files_to_delete = int(len(files) * 0.2)
            for file_path, _ in files[:files_to_delete]:
                os.remove(file_path)
                self.logger.debug(f"删除旧文件: {file_path}")
                
        except Exception as e:
            self.logger.error(f"清理文件失败: {e}")
    
    async def should_take_screenshot(
        self, 
        tab_id: str, 
        view_count: int,
        is_error: bool = False,
        is_first: bool = False,
        is_final: bool = False
    ) -> tuple[bool, ScreenshotType]:
        """
        判断是否应该截图
        
        Returns:
            (should_screenshot, screenshot_type)
        """
        if not self.config.enabled:
            return False, None
        
        # 检查存储限制
        if not self._check_storage_limit():
            return False, None
        
        # 错误时截图
        if is_error and self.config.error_screenshot:
            return True, ScreenshotType.ERROR
        
        # 首次访问截图
        if is_first and self.config.first_screenshot:
            return True, ScreenshotType.FIRST_LOAD
        
        # 任务完成截图
        if is_final and self.config.final_screenshot:
            return True, ScreenshotType.FINAL
        
        # 调试模式：频繁截图
        if self.config.debug_mode:
            tab_screenshots = self.screenshot_count.get(tab_id, 0)
            if tab_screenshots < self.config.debug_max_screenshots:
                if view_count % self.config.debug_interval == 0:
                    return True, ScreenshotType.DEBUG
        
        # 里程碑截图
        if view_count > 0 and view_count % self.config.milestone_interval == 0:
            return True, ScreenshotType.MILESTONE
        
        return False, None
    
    async def take_screenshot(
        self,
        page,
        tab_id: str,
        view_count: int,
        screenshot_type: ScreenshotType,
        error_msg: Optional[str] = None
    ) -> Optional[str]:
        """
        执行截图
        
        Returns:
            截图文件路径，失败返回None
        """
        try:
            # 更新计数
            self.screenshot_count[tab_id] = self.screenshot_count.get(tab_id, 0) + 1
            self.total_screenshots += 1
            
            # 生成文件名
            timestamp = datetime.now().strftime("%H%M%S")
            type_suffix = screenshot_type.value
            filename = f"{tab_id}_v{view_count}_{type_suffix}_{timestamp}.png"
            filepath = self.current_dir / filename
            
            # 执行截图
            await page.screenshot(path=str(filepath), full_page=False)
            
            # 记录日志
            if screenshot_type == ScreenshotType.ERROR:
                self.logger.error(f"❌ 错误截图: {filepath} - {error_msg}")
            elif screenshot_type == ScreenshotType.MILESTONE:
                self.logger.info(f"🎯 里程碑截图: {filepath} (第{view_count}次访问)")
            elif screenshot_type == ScreenshotType.FIRST_LOAD:
                self.logger.info(f"🚀 首次访问截图: {filepath}")
            elif screenshot_type == ScreenshotType.FINAL:
                self.logger.info(f"🏁 任务完成截图: {filepath}")
            elif screenshot_type == ScreenshotType.DEBUG:
                self.logger.debug(f"🔍 调试截图: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"截图失败: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取截图统计信息"""
        try:
            total_size = 0
            total_files = 0
            
            if Path(self.config.base_dir).exists():
                for root, dirs, files in os.walk(self.config.base_dir):
                    png_files = [f for f in files if f.endswith('.png')]
                    total_files += len(png_files)
                    for file in png_files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
            
            return {
                "enabled": self.config.enabled,
                "debug_mode": self.config.debug_mode,
                "total_screenshots": self.total_screenshots,
                "total_files": total_files,
                "storage_mb": round(total_size / (1024 * 1024), 2),
                "max_storage_mb": self.config.max_storage_mb,
                "retention_hours": self.config.retention_hours
            }
        except Exception as e:
            self.logger.error(f"获取统计失败: {e}")
            return {}
    
    async def cleanup(self):
        """清理任务"""
        self._cleanup_old_directories()
        self.logger.info(f"📊 截图统计: {self.get_stats()}")


# 环境配置预设
def get_screenshot_config(env: str = "production") -> ScreenshotConfig:
    """根据环境获取截图配置"""
    
    configs = {
        "production": ScreenshotConfig(
            enabled=True,
            debug_mode=False,
            max_storage_mb=50,
            retention_hours=12,
            milestone_interval=100,
            error_screenshot=True,
            first_screenshot=True,
            final_screenshot=True
        ),
        "staging": ScreenshotConfig(
            enabled=True,
            debug_mode=False,
            max_storage_mb=100,
            retention_hours=24,
            milestone_interval=50,
            error_screenshot=True,
            first_screenshot=True,
            final_screenshot=True
        ),
        "development": ScreenshotConfig(
            enabled=True,
            debug_mode=True,
            max_storage_mb=200,
            retention_hours=48,
            milestone_interval=20,
            debug_interval=5,
            debug_max_screenshots=50
        ),
        "disabled": ScreenshotConfig(
            enabled=False
        )
    }
    
    return configs.get(env, configs["production"])