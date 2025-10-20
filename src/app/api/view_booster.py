"""
多URL浏览量提升API路由 v2.0 - 简化版
基于twitter_booster.py简化设计，支持多URL并发处理
"""

import asyncio
from flask import request, jsonify, current_app, Blueprint

from ..services.view_booster import (
    MultiURLViewBooster,
    ViewBoosterConfig,
    FastViewBooster,
    FastBoosterConfig,
    AccountManager
)
from ..services.view_booster.task_manager import task_manager


# 创建浏览量提升API蓝图
view_booster_bp = Blueprint('view_booster', __name__, url_prefix='/api/v1/view-booster')


def get_account_manager() -> AccountManager:
    """获取账户管理器实例"""
    if not hasattr(current_app, 'account_manager'):
        current_app.account_manager = AccountManager()
    return current_app.account_manager


@view_booster_bp.route('/health')
def health_check():
    """健康检查"""
    try:
        account_manager = get_account_manager()
        active_accounts = len(account_manager.get_active_accounts())
        
        return jsonify({
            "success": True,
            "message": "Multi-URL view booster service is running",
            "service": "view_booster_multi_url",
            "version": "2.0.0",
            "active_accounts": active_accounts
        })
    except Exception as e:
        current_app.logger.error(f"健康检查失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Health check failed: {str(e)}"
        }), 500




@view_booster_bp.route('/accounts/status')
def get_accounts_status():
    """获取账户状态"""
    try:
        account_manager = get_account_manager()
        
        # 获取统计信息
        stats = account_manager.get_statistics()
        
        # 获取账户验证结果
        validation_result = account_manager.validate_all_accounts()
        
        return jsonify({
            "success": True,
            "data": {
                "statistics": stats,
                "validation": validation_result,
                "service_version": "2.0.0"
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"获取账户状态失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to get account status: {str(e)}"
        }), 500




@view_booster_bp.route('/boost', methods=['POST'])
def boost_views():
    """多URL浏览量提升 - 立即返回任务ID"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Request body is required"
            }), 400
        
        # 解析URL参数
        urls = data.get('urls', [])
        if isinstance(urls, str):
            urls = [urls]
        
        if not urls:
            return jsonify({
                "success": False,
                "error": "At least one URL is required"
            }), 400
        
        # 验证URL格式
        valid_urls = [url for url in urls if isinstance(url, str) and ('twitter.com' in url or 'x.com' in url)]
        
        if not valid_urls:
            return jsonify({
                "success": False,
                "error": "No valid Twitter/X URLs provided"
            }), 400
        
        # 配置参数
        config = ViewBoosterConfig(
            target_urls=valid_urls,
            max_concurrent_instances=min(data.get('max_instances', 3), 10),
            max_tabs_per_instance=min(data.get('max_tabs_per_instance', 3), 5),
            refresh_interval=max(data.get('refresh_interval', 10), 5),
            proxy=data.get('proxy'),
            headless=data.get('headless', True),
            use_proxy_pool=data.get('use_proxy_pool', False),
            target_views=max(data.get('target_views', 100), 1)
        )
        
        # 在主线程中获取账户管理器（避免上下文问题）
        account_manager = get_account_manager()
        
        # 创建任务
        task_id = task_manager.create_task("view_boost")
        
        # 定义异步任务函数
        async def run_boost_task():
            # 使用传入的账户管理器
            
            # 创建进度回调
            def progress_callback(progress):
                task_manager.update_task(task_id, {"progress": progress})
            
            # 修改MultiURLViewBooster以支持progress_callback
            booster = MultiURLViewBooster(config, account_manager)
            
            # 保存booster实例以便停止
            task_manager.set_booster(task_id, booster)
            
            # 定期更新进度
            async def update_progress():
                while booster.running:
                    progress = {
                        "successful_views": booster.stats.get('successful_views', 0),
                        "total_views": booster.stats.get('total_views', 0),
                        "failed_views": booster.stats.get('failed_views', 0),
                        "target_views": config.target_views,
                        "progress_percentage": (booster.stats.get('successful_views', 0) / config.target_views) * 100
                    }
                    task_manager.update_task(task_id, {"progress": progress})
                    await asyncio.sleep(2)  # 每2秒更新一次
            
            # 启动进度更新任务
            progress_task = asyncio.create_task(update_progress())
            
            try:
                # 运行主任务
                result = await booster.start_boost(valid_urls)
                return result
            finally:
                progress_task.cancel()
        
        # 在后台运行任务
        task_manager.run_async_task(task_id, run_boost_task)
        
        # 立即返回任务ID
        return jsonify({
            "success": True,
            "message": "View boost task started successfully",
            "data": {
                "task_id": task_id,
                "status_url": f"/api/v1/view-booster/tasks/{task_id}",
                "config": {
                    "urls": valid_urls,
                    "target_views": config.target_views,
                    "max_instances": config.max_concurrent_instances,
                    "max_tabs_per_instance": config.max_tabs_per_instance,
                    "use_proxy_pool": config.use_proxy_pool
                }
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"浏览量提升异常: {e}")
        return jsonify({
            "success": False,
            "error": f"Service error: {str(e)}"
        }), 500


@view_booster_bp.route('/tasks')
def get_all_tasks():
    """获取所有任务列表"""
    try:
        tasks = task_manager.get_all_tasks()
        
        # 格式化响应
        formatted_tasks = []
        for task in tasks:
            formatted_tasks.append({
                "task_id": task["id"],
                "type": task.get("type", "view_boost"),
                "status": task["status"],
                "created_at": task["created_at"].isoformat() if task["created_at"] else None,
                "started_at": task["started_at"].isoformat() if task.get("started_at") else None,
                "completed_at": task["completed_at"].isoformat() if task.get("completed_at") else None,
                "progress": task.get("progress", {})
            })
        
        return jsonify({
            "success": True,
            "data": {
                "total": len(formatted_tasks),
                "tasks": formatted_tasks
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"获取任务列表失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to get tasks: {str(e)}"
        }), 500


@view_booster_bp.route('/tasks/<task_id>')
def get_task_status(task_id):
    """获取任务状态"""
    try:
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({
                "success": False,
                "error": f"Task not found: {task_id}"
            }), 404
        
        # 格式化响应
        response = {
            "success": True,
            "data": {
                "task_id": task["id"],
                "status": task["status"],
                "created_at": task["created_at"].isoformat() if task["created_at"] else None,
                "started_at": task["started_at"].isoformat() if task["started_at"] else None,
                "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None,
                "progress": task.get("progress", {}),
                "result": task.get("result"),
                "error": task.get("error")
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"获取任务状态失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to get task status: {str(e)}"
        }), 500


@view_booster_bp.route('/tasks/<task_id>/stop', methods=['POST'])
def stop_task(task_id):
    """停止任务"""
    try:
        success = task_manager.stop_task(task_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Task {task_id} is stopping",
                "data": {
                    "task_id": task_id,
                    "status": "stopping"
                }
            })
        else:
            task = task_manager.get_task(task_id)
            if not task:
                return jsonify({
                    "success": False,
                    "error": f"Task not found: {task_id}"
                }), 404
            elif task["status"] in ["stopped", "completed", "failed"]:
                return jsonify({
                    "success": False,
                    "error": f"Task already finished, status: {task['status']}"
                }), 400
            else:
                return jsonify({
                    "success": False,
                    "error": f"Task status is {task['status']}, cannot stop"
                }), 400
                
    except Exception as e:
        current_app.logger.error(f"停止任务失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to stop task: {str(e)}"
        }), 500


@view_booster_bp.route('/fast-start', methods=['POST'])
def fast_start():
    """Fast view boost without browser - High speed mode"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Request body is required"
            }), 400
        
        # Parse URLs
        urls = data.get('urls', [])
        if isinstance(urls, str):
            urls = [urls]
        
        if not urls:
            # Legacy support for single URL
            tweet_url = data.get('tweet_url')
            if tweet_url:
                urls = [tweet_url]
        
        if not urls:
            return jsonify({
                "success": False,
                "error": "At least one URL is required"
            }), 400
        
        # Validate URLs
        valid_urls = []
        for url in urls:
            if 'twitter.com' in url or 'x.com' in url:
                valid_urls.append(url)
            else:
                current_app.logger.warning(f"Invalid URL: {url}")
        
        if not valid_urls:
            return jsonify({
                "success": False,
                "error": "No valid Twitter/X URLs provided"
            }), 400
        
        # Create config
        config = FastBoosterConfig(
            target_urls=valid_urls,
            target_views=data.get('target_views', 1000),
            max_concurrent_requests=data.get('max_concurrent_requests', 10),
            request_interval=data.get('request_interval', (1, 3)),
            use_proxy_pool=data.get('use_proxy_pool', True),
            proxy=data.get('proxy'),  # 添加单一代理参数支持
            timeout=data.get('timeout', 10),
            retry_on_failure=data.get('retry_on_failure', True),
            max_retries=data.get('max_retries', 3)
        )
        
        # Get account manager in main thread
        account_manager = get_account_manager()
        
        # Create task
        task_id = task_manager.create_task("fast_view_boost")
        
        async def run_fast_boost_task():
            """Run fast boost task asynchronously"""
            # Create booster instance
            booster = FastViewBooster(config, account_manager)
            task_manager.boosters[task_id] = booster
            
            # Update task status
            task_manager.update_task(task_id, {"status": "running"})
            
            # Progress update task
            async def update_progress():
                while booster.running:
                    stats = booster.get_stats()
                    task_manager.update_task(task_id, {"progress": stats})
                    await asyncio.sleep(1)  # Update every second
            
            # Start progress updater
            progress_task = asyncio.create_task(update_progress())
            
            try:
                # Run the fast booster
                await booster.start()
                
                # Get final stats
                final_stats = booster.get_stats()
                task_manager.update_task(task_id, {
                    "status": "completed",
                    "result": final_stats
                })
                return final_stats
            except Exception as e:
                task_manager.update_task(task_id, {
                    "status": "failed",
                    "error": str(e)
                })
                raise
            finally:
                progress_task.cancel()
                # Clean up
                if task_id in task_manager.boosters:
                    del task_manager.boosters[task_id]
        
        # Run task in background
        task_manager.run_async_task(task_id, run_fast_boost_task)
        
        # Return immediately with task ID
        return jsonify({
            "success": True,
            "message": "Fast view boost task started successfully",
            "data": {
                "task_id": task_id,
                "status_url": f"/api/v1/view-booster/tasks/{task_id}",
                "mode": "fast_no_browser",
                "config": {
                    "urls": valid_urls,
                    "target_views": config.target_views,
                    "max_concurrent_requests": config.max_concurrent_requests,
                    "use_proxy_pool": config.use_proxy_pool,
                    "proxy": config.proxy,
                    "request_interval": config.request_interval
                }
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Fast boost error: {e}")
        return jsonify({
            "success": False,
            "error": f"Service error: {str(e)}"
        }), 500


@view_booster_bp.route('/config')
def get_config():
    """获取当前配置信息"""
    try:
        account_manager = get_account_manager()
        active_accounts = len(account_manager.get_active_accounts())
        
        return jsonify({
            "success": True,
            "data": {
                "service": "multi_url_view_booster",
                "version": "2.0.0",
                "available_accounts": active_accounts,
                "limits": {
                    "max_instances": 10,
                    "max_tabs_per_instance": 5,
                    "min_refresh_interval": 5,
                    "max_timeout": 600
                },
                "supported_parameters": {
                    "urls": "List of Twitter/X URLs",
                    "tweet_url": "Single URL (legacy compatibility)",
                    "max_instances": "Maximum browser instances (1-10)",
                    "max_tabs_per_instance": "Maximum tabs per instance (1-5)",
                    "refresh_interval": "Refresh interval in seconds (min 5)",
                    "proxy": "Proxy URL (optional, ignored if use_proxy_pool=true)",
                    "headless": "Run in headless mode (default: true)",
                    "use_proxy_pool": "Use proxy pool for different proxies per instance (default: false)",
                    "target_views": "Target view count, task stops when reached (default: 100, min: 1)"
                }
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"获取配置失败: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to get config: {str(e)}"
        }), 500


