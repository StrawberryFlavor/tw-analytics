"""
数据更新调度器

遵循开闭原则，提供灵活的调度策略
支持定时更新、条件触发更新和手动更新
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from .service import TweetDataUpdater, UpdateResult
from ...core.config_factory import UpdaterConfig
from .progress_tracker import UpdateStatus


class ScheduleType(Enum):
    """调度类型枚举"""
    MANUAL = "manual"           # 手动触发
    INTERVAL = "interval"       # 定时间隔
    DAILY = "daily"            # 每日定时
    WEEKLY = "weekly"          # 每周定时
    CONDITION = "condition"     # 条件触发


@dataclass
class ScheduleConfig:
    """调度配置"""
    schedule_type: ScheduleType
    interval_hours: Optional[int] = None
    daily_hour: Optional[int] = None  # 0-23
    weekly_day: Optional[int] = None  # 0-6 (Monday=0)
    weekly_hour: Optional[int] = None
    condition_check_interval: Optional[int] = None  # 分钟
    max_retries: int = 3
    retry_delay_minutes: int = 30
    
    def validate(self) -> tuple[bool, str]:
        """验证调度配置"""
        if self.schedule_type == ScheduleType.INTERVAL:
            if not self.interval_hours or self.interval_hours <= 0:
                return False, "间隔调度需要设置 interval_hours > 0"
        
        elif self.schedule_type == ScheduleType.DAILY:
            if self.daily_hour is None or not (0 <= self.daily_hour <= 23):
                return False, "每日调度需要设置 daily_hour (0-23)"
        
        elif self.schedule_type == ScheduleType.WEEKLY:
            if (self.weekly_day is None or not (0 <= self.weekly_day <= 6) or
                self.weekly_hour is None or not (0 <= self.weekly_hour <= 23)):
                return False, "每周调度需要设置 weekly_day (0-6) 和 weekly_hour (0-23)"
        
        elif self.schedule_type == ScheduleType.CONDITION:
            if not self.condition_check_interval or self.condition_check_interval <= 0:
                return False, "条件调度需要设置 condition_check_interval > 0"
        
        return True, ""


@dataclass
class ScheduleStatus:
    """调度状态"""
    is_running: bool = False
    is_paused: bool = False
    last_run_time: Optional[datetime] = None
    next_run_time: Optional[datetime] = None
    last_result: Optional[UpdateResult] = None
    run_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0


class UpdateScheduler:
    """数据更新调度器 - 单一职责原则"""
    
    def __init__(self, 
                 updater: TweetDataUpdater,
                 schedule_config: ScheduleConfig,
                 condition_checker: Optional[Callable[[], bool]] = None):
        """
        初始化调度器
        
        Args:
            updater: 数据更新器
            schedule_config: 调度配置
            condition_checker: 条件检查器（用于条件触发）
        """
        self.updater = updater
        self.schedule_config = schedule_config
        self.condition_checker = condition_checker
        
        # 验证配置
        is_valid, error_msg = schedule_config.validate()
        if not is_valid:
            raise ValueError(f"调度配置无效: {error_msg}")
        
        self.logger = logging.getLogger(__name__)
        
        # 状态管理
        self.status = ScheduleStatus()
        self._schedule_task: Optional[asyncio.Task] = None
        self._should_stop = False
        
        # 回调函数
        self._before_update_callbacks: List[Callable[[], None]] = []
        self._after_update_callbacks: List[Callable[[UpdateResult], None]] = []
        self._error_callbacks: List[Callable[[Exception], None]] = []
        
        self.logger.info(f"调度器初始化完成: {schedule_config.schedule_type.value}")
    
    def start(self):
        """启动调度器"""
        if self.status.is_running:
            self.logger.warning("调度器已在运行")
            return
        
        if self.schedule_config.schedule_type == ScheduleType.MANUAL:
            self.logger.info("手动调度模式，等待手动触发")
            return
        
        self._should_stop = False
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        self.status.is_running = True
        
        self.logger.info(f"调度器已启动: {self.schedule_config.schedule_type.value}")
        
        # 计算下次运行时间
        self._update_next_run_time()
    
    def stop(self):
        """停止调度器"""
        self._should_stop = True
        
        if self._schedule_task:
            self._schedule_task.cancel()
            self._schedule_task = None
        
        self.status.is_running = False
        self.status.is_paused = False
        
        self.logger.info("调度器已停止")
    
    def pause(self):
        """暂停调度器"""
        self.status.is_paused = True
        self.logger.info("调度器已暂停")
    
    def resume(self):
        """恢复调度器"""
        self.status.is_paused = False
        self.logger.info("调度器已恢复")
    
    async def trigger_manual_update(self, **kwargs) -> UpdateResult:
        """手动触发更新"""
        self.logger.info("手动触发数据更新...")
        
        try:
            # 执行更新前回调
            self._execute_before_update_callbacks()
            
            # 执行更新
            result = await self.updater.update_all_records(**kwargs)
            
            # 更新状态
            self._update_status_after_run(result)
            
            # 执行更新后回调
            self._execute_after_update_callbacks(result)
            
            self.logger.info(f"手动更新完成: {result.successful_updates}/{result.total_records} 成功")
            
            return result
            
        except Exception as e:
            self.status.failure_count += 1
            self.status.consecutive_failures += 1
            
            # 执行错误回调
            self._execute_error_callbacks(e)
            
            self.logger.error(f"手动更新失败: {e}")
            raise
    
    async def _schedule_loop(self):
        """调度循环"""
        try:
            while not self._should_stop:
                # 检查暂停状态
                if self.status.is_paused:
                    await asyncio.sleep(60)  # 暂停时每分钟检查一次
                    continue
                
                # 检查是否到了运行时间
                if self._should_run_now():
                    await self._execute_scheduled_update()
                
                # 等待下次检查
                await asyncio.sleep(self._get_check_interval())
                
        except asyncio.CancelledError:
            self.logger.info("调度循环已取消")
        except Exception as e:
            self.logger.error(f"调度循环异常: {e}")
            self._execute_error_callbacks(e)
    
    def _should_run_now(self) -> bool:
        """检查是否应该现在运行"""
        now = datetime.now()
        
        # 检查是否已设置下次运行时间
        if self.status.next_run_time and now < self.status.next_run_time:
            return False
        
        if self.schedule_config.schedule_type == ScheduleType.INTERVAL:
            if not self.status.last_run_time:
                return True  # 首次运行
            
            elapsed = now - self.status.last_run_time
            return elapsed.total_seconds() >= self.schedule_config.interval_hours * 3600
        
        elif self.schedule_config.schedule_type == ScheduleType.DAILY:
            if (now.hour == self.schedule_config.daily_hour and 
                (not self.status.last_run_time or 
                 self.status.last_run_time.date() < now.date())):
                return True
        
        elif self.schedule_config.schedule_type == ScheduleType.WEEKLY:
            if (now.weekday() == self.schedule_config.weekly_day and
                now.hour == self.schedule_config.weekly_hour and
                (not self.status.last_run_time or 
                 (now - self.status.last_run_time).days >= 7)):
                return True
        
        elif self.schedule_config.schedule_type == ScheduleType.CONDITION:
            if self.condition_checker and self.condition_checker():
                # 避免频繁触发，至少间隔1小时
                if (not self.status.last_run_time or 
                    (now - self.status.last_run_time).total_seconds() >= 3600):
                    return True
        
        return False
    
    async def _execute_scheduled_update(self):
        """执行调度的更新"""
        retry_count = 0
        
        while retry_count <= self.schedule_config.max_retries:
            try:
                self.logger.info(f"执行调度更新 (尝试 {retry_count + 1}/{self.schedule_config.max_retries + 1})")
                
                # 执行更新前回调
                self._execute_before_update_callbacks()
                
                # 执行更新
                result = await self.updater.update_all_records()
                
                # 更新状态
                self._update_status_after_run(result)
                
                # 执行更新后回调
                self._execute_after_update_callbacks(result)
                
                self.logger.info(f"调度更新完成: {result.successful_updates}/{result.total_records} 成功")
                
                # 重置连续失败计数
                self.status.consecutive_failures = 0
                
                # 更新下次运行时间
                self._update_next_run_time()
                
                return
                
            except Exception as e:
                retry_count += 1
                self.status.failure_count += 1
                self.status.consecutive_failures += 1
                
                self.logger.error(f"调度更新失败 (尝试 {retry_count}): {e}")
                
                if retry_count <= self.schedule_config.max_retries:
                    delay_seconds = self.schedule_config.retry_delay_minutes * 60
                    self.logger.info(f"{delay_seconds/60:.0f} 分钟后重试...")
                    await asyncio.sleep(delay_seconds)
                else:
                    # 执行错误回调
                    self._execute_error_callbacks(e)
                    
                    # 仍然更新下次运行时间，避免卡住
                    self._update_next_run_time()
                    break
    
    def _update_status_after_run(self, result: UpdateResult):
        """更新运行后的状态"""
        self.status.last_run_time = datetime.now()
        self.status.last_result = result
        self.status.run_count += 1
    
    def _update_next_run_time(self):
        """更新下次运行时间"""
        now = datetime.now()
        
        if self.schedule_config.schedule_type == ScheduleType.INTERVAL:
            self.status.next_run_time = now + timedelta(hours=self.schedule_config.interval_hours)
        
        elif self.schedule_config.schedule_type == ScheduleType.DAILY:
            # 计算明天的指定小时
            next_run = now.replace(hour=self.schedule_config.daily_hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            self.status.next_run_time = next_run
        
        elif self.schedule_config.schedule_type == ScheduleType.WEEKLY:
            # 计算下周的指定时间
            days_ahead = self.schedule_config.weekly_day - now.weekday()
            if days_ahead <= 0:  # 本周已过或当天
                days_ahead += 7
            
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=self.schedule_config.weekly_hour, minute=0, second=0, microsecond=0)
            self.status.next_run_time = next_run
        
        elif self.schedule_config.schedule_type == ScheduleType.CONDITION:
            # 条件触发没有固定的下次运行时间
            self.status.next_run_time = None
    
    def _get_check_interval(self) -> int:
        """获取检查间隔（秒）"""
        if self.schedule_config.schedule_type == ScheduleType.CONDITION:
            return self.schedule_config.condition_check_interval * 60
        else:
            return 300  # 5分钟检查一次
    
    def _execute_before_update_callbacks(self):
        """执行更新前回调"""
        for callback in self._before_update_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"更新前回调异常: {e}")
    
    def _execute_after_update_callbacks(self, result: UpdateResult):
        """执行更新后回调"""
        for callback in self._after_update_callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"更新后回调异常: {e}")
    
    def _execute_error_callbacks(self, error: Exception):
        """执行错误回调"""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                self.logger.error(f"错误回调异常: {e}")
    
    def add_before_update_callback(self, callback: Callable[[], None]):
        """添加更新前回调"""
        self._before_update_callbacks.append(callback)
    
    def add_after_update_callback(self, callback: Callable[[UpdateResult], None]):
        """添加更新后回调"""
        self._after_update_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[Exception], None]):
        """添加错误回调"""
        self._error_callbacks.append(callback)
    
    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            'schedule_type': self.schedule_config.schedule_type.value,
            'is_running': self.status.is_running,
            'is_paused': self.status.is_paused,
            'last_run_time': self.status.last_run_time.isoformat() if self.status.last_run_time else None,
            'next_run_time': self.status.next_run_time.isoformat() if self.status.next_run_time else None,
            'run_count': self.status.run_count,
            'failure_count': self.status.failure_count,
            'consecutive_failures': self.status.consecutive_failures,
            'last_result_summary': {
                'total_records': self.status.last_result.total_records,
                'successful_updates': self.status.last_result.successful_updates,
                'success_rate': self.status.last_result.success_rate,
                'processing_time': self.status.last_result.processing_time
            } if self.status.last_result else None
        }


# 便捷工厂方法

def create_daily_scheduler(updater: TweetDataUpdater, 
                          hour: int = 2) -> UpdateScheduler:
    """创建每日调度器"""
    config = ScheduleConfig(
        schedule_type=ScheduleType.DAILY,
        daily_hour=hour
    )
    return UpdateScheduler(updater, config)

def create_interval_scheduler(updater: TweetDataUpdater, 
                            interval_hours: int = 6) -> UpdateScheduler:
    """创建间隔调度器"""
    config = ScheduleConfig(
        schedule_type=ScheduleType.INTERVAL,
        interval_hours=interval_hours
    )
    return UpdateScheduler(updater, config)

def create_condition_scheduler(updater: TweetDataUpdater,
                             condition_checker: Callable[[], bool],
                             check_interval_minutes: int = 30) -> UpdateScheduler:
    """创建条件调度器"""
    config = ScheduleConfig(
        schedule_type=ScheduleType.CONDITION,
        condition_check_interval=check_interval_minutes
    )
    return UpdateScheduler(updater, config, condition_checker)
