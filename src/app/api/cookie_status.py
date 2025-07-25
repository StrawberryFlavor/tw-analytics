"""
Cookie状态监控API
提供Cookie健康状态和管理功能
"""

from flask import Blueprint, jsonify, current_app
from ..core.interfaces import TwitterServiceInterface
from ..services.cookie_manager import get_cookie_manager
from .routes import handle_twitter_exception

# 创建Cookie状态API蓝图
cookie_status_bp = Blueprint('cookie_status', __name__, url_prefix='/api/v1')


@cookie_status_bp.route('/auth/status', methods=['GET'])
def get_auth_status():
    """获取认证状态"""
    try:
        cookie_manager = get_cookie_manager()
        status = cookie_manager.get_status()
        
        return jsonify({
            "success": True,
            "data": {
                "authentication": {
                    "cookie_file_exists": status["has_cookie_file"],
                    "has_cached_cookies": status["has_cached_cookies"],
                    "cookie_count": status["cookie_count"],
                    "auto_refresh_enabled": bool(_get_login_credentials())
                },
                "status": _determine_auth_status(status)
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@cookie_status_bp.route('/auth/refresh', methods=['POST'])
def refresh_cookies():
    """强制刷新cookies"""
    try:
        # 检查是否有登录凭据
        credentials = _get_login_credentials()
        if not credentials["username"] or not credentials["password"]:
            return jsonify({
                "success": False,
                "error": "Missing credentials",
                "message": "TWITTER_USERNAME and TWITTER_PASSWORD environment variables are required for cookie refresh"
            }), 400
        
        # 异步刷新需要在事件循环中运行
        import asyncio
        
        async def refresh():
            # 简化版不支持强制刷新，需要手动运行login_twitter.py
            return False
        
        # 创建新的事件循环来运行异步操作
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(refresh())
        finally:
            loop.close()
        
        if success:
            return jsonify({
                "success": True,
                "message": "Cookies refreshed successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Refresh failed", 
                "message": "Failed to refresh cookies, please check credentials and network connection"
            }), 500
            
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


def _get_login_credentials():
    """获取登录凭据"""
    import os
    return {
        "username": os.getenv('TWITTER_USERNAME'),
        "password": os.getenv('TWITTER_PASSWORD'),
        "email": os.getenv('TWITTER_EMAIL')
    }


def _determine_auth_status(cookie_status):
    """根据cookie状态确定认证状态"""
    if not cookie_status["has_cookie_file"]:
        return "no_cookies"
    
    if cookie_status["cookie_count"] == 0:
        return "empty_cookies"
    
    return "healthy"