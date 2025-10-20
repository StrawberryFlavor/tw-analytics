"""
简单的后台任务管理器
遵循KISS原则，使用最简单的方式实现后台任务
"""

import uuid
import threading
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class TaskManager:
    """极简的任务管理器"""
    
    def __init__(self):
        self.tasks = {}  # 任务状态存储
        self.lock = threading.Lock()  # 线程安全
        self.stop_events = {}  # 停止事件
        self.boosters = {}  # 保存booster实例以便停止
    
    def create_task(self, task_type: str = "view_boost") -> str:
        """创建任务，返回任务ID"""
        task_id = str(uuid.uuid4())
        
        with self.lock:
            self.tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "status": "pending",
                "created_at": datetime.now(),
                "started_at": None,
                "completed_at": None,
                "progress": {},
                "result": None,
                "error": None
            }
        
        logger.info(f"创建任务: {task_id}")
        return task_id
    
    def update_task(self, task_id: str, updates: Dict[str, Any]):
        """更新任务状态"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(updates)
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                # 返回副本，避免线程安全问题
                return task.copy()
        return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务列表"""
        with self.lock:
            return [task.copy() for task in self.tasks.values()]
    
    def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        with self.lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task["status"] != "running":
                return False
            
            # 标记任务为正在停止
            self.tasks[task_id]["status"] = "stopping"
            self.tasks[task_id]["stopped_at"] = datetime.now()
            
            # 获取booster引用（保持在锁内以确保一致性）
            booster = self.boosters.get(task_id)
            
            # 设置停止标志
            if booster:
                # 设置running为False，booster会在下次循环时检测到并停止
                booster.running = False
                logger.info(f"已发送停止信号给任务: {task_id}")
            
            # 注意：实际的状态更新会在任务线程中完成
            # 当任务线程检测到running=False时，会自动更新状态为stopped或completed
            
            return True
    
    def set_booster(self, task_id: str, booster):
        """保存booster实例"""
        with self.lock:
            self.boosters[task_id] = booster
    
    def run_async_task(self, task_id: str, async_func, *args, **kwargs):
        """在后台线程中运行异步任务"""
        def worker():
            # 更新任务状态为运行中
            self.update_task(task_id, {
                "status": "running",
                "started_at": datetime.now()
            })
            
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # 运行异步函数
                    result = loop.run_until_complete(async_func(*args, **kwargs))
                    
                    # 检查任务当前状态，如果是stopping则更新为stopped
                    with self.lock:
                        current_status = self.tasks.get(task_id, {}).get("status")
                    
                    if current_status == "stopping":
                        # 任务是被手动停止的
                        self.update_task(task_id, {
                            "status": "stopped",
                            "completed_at": datetime.now(),
                            "result": {"message": "Task stopped by user", "data": result}
                        })
                        logger.info(f"任务已停止: {task_id}")
                    else:
                        # 任务正常完成
                        self.update_task(task_id, {
                            "status": "completed",
                            "completed_at": datetime.now(),
                            "result": result
                        })
                        logger.info(f"任务完成: {task_id}")
                    
                finally:
                    loop.close()
                    # 清理资源
                    with self.lock:
                        self.boosters.pop(task_id, None)
                        self.stop_events.pop(task_id, None)
                    
            except Exception as e:
                # 更新任务为失败
                self.update_task(task_id, {
                    "status": "failed",
                    "completed_at": datetime.now(),
                    "error": str(e)
                })
                
                logger.error(f"任务失败: {task_id} - {e}")
        
        # 在新线程中运行
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        
        return thread


# 全局实例
task_manager = TaskManager()