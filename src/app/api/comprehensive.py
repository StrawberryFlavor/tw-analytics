"""
综合数据提取API路由
"""

from flask import Blueprint, request, jsonify, current_app
import json
from ..core.interfaces import TwitterServiceInterface, ResponseFormatterInterface
from .routes import handle_twitter_exception

# 创建综合数据API蓝图，不使用版本号前缀
comprehensive_bp = Blueprint('comprehensive', __name__, url_prefix='/api')


@comprehensive_bp.route('/tweet/comprehensive', methods=['POST'])
def get_comprehensive_tweet_data():
    """获取推特页面的综合数据（包括主推文、线程、相关推文等）
    
    统一返回优化后的格式化数据，提供一致的高质量API体验
    """
    try:
        # 验证请求参数
        data = request.get_json()
        if not data or 'url' not in data:
            return _create_error_response("Invalid parameters", "URL parameter is required", 400)
        
        # 检查不支持的参数
        allowed_params = {'url'}
        provided_params = set(data.keys())
        unsupported_params = provided_params - allowed_params
        
        if unsupported_params:
            unsupported_list = ', '.join(unsupported_params)
            return _create_error_response(
                "Invalid parameters", 
                f"Unsupported parameters: {unsupported_list}. API has been optimized to only require 'url' parameter.", 
                400
            )
        
        # 从容器获取服务
        container = current_app.container
        twitter_service: TwitterServiceInterface = container.get('twitter_service')
        
        # 提取推文数据
        tweet_url = data['url']
        raw_data = twitter_service.get_comprehensive_tweet_data_sync(tweet_url)
        
        # 格式化响应数据 - 统一使用优化后的格式化器
        response_data = _format_response_data(raw_data, container)
        
        # 返回格式化的JSON响应
        return _create_json_response(response_data)
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


def _format_response_data(raw_data: dict, container) -> dict:
    """格式化响应数据 - 统一使用优化的格式化器"""
    formatter: ResponseFormatterInterface = container.get('response_formatter')
    formatted_data = formatter.format_response(raw_data)
    
    return {
        "success": True,
        "data": formatted_data,
        "message": "Comprehensive data extraction completed"
    }


def _create_json_response(data: dict):
    """创建JSON响应（确保中文字符正确显示）"""
    return current_app.response_class(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json'
    )


def _create_error_response(error: str, message: str, status_code: int):
    """创建错误响应"""
    return jsonify({
        "success": False,
        "error": error,
        "message": message
    }), status_code