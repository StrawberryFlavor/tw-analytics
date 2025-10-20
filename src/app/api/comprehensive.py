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
    
    返回统一的响应结构：user_tweet + primary_tweet双字段，
    使用action_info统一设计，确保数据一致性。
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
                f"Unsupported parameters: {unsupported_list}. Supported parameters: url", 
                400
            )
        
        # 从容器获取服务
        container = current_app.container
        twitter_service: TwitterServiceInterface = container.get('twitter_service')
        
        # 提取推文数据
        tweet_url = data['url']
        raw_data = twitter_service.get_comprehensive_data_sync(tweet_url)
        
        # 格式化响应数据
        response_data = _format_response_data(raw_data, container)
        
        # 返回格式化的JSON响应
        return _create_json_response(response_data)
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


def _format_response_data(raw_data: dict, container) -> dict:
    """格式化响应数据"""
    # 使用统一的格式化器
    from ..services.formatters.response_formatter import TweetResponseFormatter
    formatter = TweetResponseFormatter()
    formatted_data = formatter.format_response(raw_data)
    
    # 增强数据：为primary_tweet获取真实metrics
    formatted_data = _enhance_primary_tweet_data(formatted_data, container)
    
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


def _enhance_primary_tweet_data(formatted_data: dict, container) -> dict:
    """增强primary_tweet的数据（获取真实metrics）
    
    遵循单一职责原则，在API层处理数据增强。
    """
    try:
        primary_tweet = formatted_data.get('primary_tweet')
        if not primary_tweet or not primary_tweet.get('_enhance_with_real_data'):
            return formatted_data
        
        real_tweet_url = primary_tweet.get('_real_tweet_url')
        if not real_tweet_url:
            return formatted_data
        
        # 使用TwitterService获取真实数据
        twitter_service = container.get('twitter_service')
        real_data = twitter_service.get_comprehensive_data_sync(real_tweet_url)
        
        if real_data and real_data.get('primary_tweet'):
            real_tweet = real_data['primary_tweet']
            
            # 更新metrics数据 - 确保从真实数据中获取
            real_metrics = real_tweet.get('metrics')
            if real_metrics and isinstance(real_metrics, dict):
                # 创建一个新的metrics对象，确保数据类型正确
                enhanced_metrics = {
                    'likes': int(real_metrics.get('likes', 0)),
                    'retweets': int(real_metrics.get('retweets', 0)), 
                    'replies': int(real_metrics.get('replies', 0)),
                    'quotes': int(real_metrics.get('quotes', 0)),
                    'views': int(real_metrics.get('views', 0))
                }
                primary_tweet['metrics'] = enhanced_metrics
            
            # 更新时间戳（如果需要）
            if not primary_tweet.get('time') and real_tweet.get('timestamp'):
                primary_tweet['time'] = real_tweet['timestamp']
            
            # 更新作者信息（如果需要）
            if real_tweet.get('author') and not primary_tweet.get('author', {}).get('name'):
                real_author = real_tweet['author']
                if isinstance(real_author, dict):
                    primary_tweet['author'].update({
                        'name': real_author.get('display_name') or real_author.get('name'),
                        'avatar': real_author.get('avatar_url') or primary_tweet['author'].get('avatar'),
                        'verified': real_author.get('is_verified', primary_tweet['author'].get('verified', False))
                    })
        
        # 清理内部标记
        primary_tweet.pop('_enhance_with_real_data', None)
        primary_tweet.pop('_real_tweet_url', None)
        
        return formatted_data
        
    except Exception as e:
        # 如果增强失败，返回原数据并清理标记
        if 'primary_tweet' in formatted_data and formatted_data['primary_tweet']:
            formatted_data['primary_tweet'].pop('_enhance_with_real_data', None) 
            formatted_data['primary_tweet'].pop('_real_tweet_url', None)
        return formatted_data


def _create_error_response(error: str, message: str, status_code: int):
    """创建错误响应"""
    return jsonify({
        "success": False,
        "error": error,
        "message": message
    }), status_code