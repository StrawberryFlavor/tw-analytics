"""
Flask API路由
"""

from flask import request, jsonify, current_app
from . import bp
from ..services import TwitterServiceError, NotFoundError, RateLimitError, AuthenticationError


def handle_twitter_exception(e: Exception) -> tuple[dict, int]:
    """处理Twitter异常"""
    if isinstance(e, NotFoundError):
        return {"success": False, "error": "Resource not found", "message": str(e)}, 404
    elif isinstance(e, RateLimitError):
        return {"success": False, "error": "Rate limit exceeded", "message": str(e)}, 429
    elif isinstance(e, AuthenticationError):
        return {"success": False, "error": "Authentication failed", "message": str(e)}, 401
    elif isinstance(e, TwitterServiceError):
        return {"success": False, "error": "Twitter service error", "message": str(e)}, 400
    elif isinstance(e, ValueError):
        return {"success": False, "error": "Invalid parameters", "message": str(e)}, 400
    else:
        current_app.logger.error(f"Unknown error: {e}")
        return {"success": False, "error": "Internal server error", "message": "Service temporarily unavailable"}, 500


@bp.route('/health')
def health_check():
    """健康检查"""
    return jsonify({
        "success": True,
        "message": "Service is running normally",
        "version": "2.0.0"
    })


@bp.route('/tweet/<tweet_id>/views')
def get_tweet_views(tweet_id: str):
    """获取推特浏览量"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        views = twitter_service.get_tweet_views_sync(tweet_id)
        
        return jsonify({
            "success": True,
            "data": {
                "tweet_id": tweet_id,
                "views": views
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweet/by-url', methods=['POST'])
def get_tweet_by_url():
    """通过URL获取推特信息"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "URL parameter is required"
            }), 400
        
        tweet_url = data['url']
        twitter_service = current_app.container.get('twitter_service')
        tweet_data = twitter_service.get_tweet_by_url_sync(tweet_url)
        
        # Convert to dict for JSON serialization
        tweet_dict = {
            "tweet_id": tweet_data.tweet_id,
            "text": tweet_data.text,
            "author_username": tweet_data.author_username,
            "author_name": tweet_data.author_name,
            "created_at": tweet_data.created_at,
            "public_metrics": tweet_data.public_metrics,
            "view_count": tweet_data.view_count,
            "url": tweet_data.url,
            "lang": tweet_data.lang,
            "engagement_rate": tweet_data.engagement_rate
        }
        
        return jsonify({
            "success": True,
            "data": tweet_dict
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweets/by-urls', methods=['POST'])
def batch_get_tweets_by_urls():
    """批量通过URL获取推特信息"""
    try:
        data = request.get_json()
        if not data or 'urls' not in data:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "URLs array is required"
            }), 400
        
        tweet_urls = data['urls']
        if not isinstance(tweet_urls, list):
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "URLs must be an array"
            }), 400
        
        if len(tweet_urls) > current_app.config['MAX_BATCH_SIZE']:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": f"Batch requests support maximum {current_app.config['MAX_BATCH_SIZE']} URLs"
            }), 400
        
        twitter_service = current_app.container.get('twitter_service')
        tweets_data = twitter_service.batch_get_tweets_by_urls_sync(tweet_urls)
        
        # Convert to list of dicts for JSON serialization
        tweets_list = [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in tweets_data
        ]
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(tweets_list),
                "tweets": tweets_list
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweet/comprehensive', methods=['POST'])
def get_comprehensive_tweet_data():
    """获取推特页面的综合数据（包括主推文、线程、相关推文等）"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "URL parameter is required"
            }), 400
        
        tweet_url = data['url']
        twitter_service = current_app.container.get('twitter_service')
        comprehensive_data = twitter_service.get_comprehensive_tweet_data_sync(tweet_url)
        
        return jsonify({
            "success": True,
            "data": comprehensive_data,
            "message": "Comprehensive data extraction completed"
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweet/<tweet_id>')
def get_tweet_info(tweet_id: str):
    """获取推特完整信息"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        tweet_data = twitter_service.get_tweet_metrics_sync(tweet_id)
        
        # Convert to dict for JSON serialization
        tweet_dict = {
            "tweet_id": tweet_data.tweet_id,
            "text": tweet_data.text,
            "author_username": tweet_data.author_username,
            "author_name": tweet_data.author_name,
            "created_at": tweet_data.created_at,
            "public_metrics": tweet_data.public_metrics,
            "view_count": tweet_data.view_count,
            "url": tweet_data.url,
            "lang": tweet_data.lang,
            "engagement_rate": tweet_data.engagement_rate
        }
        
        return jsonify({
            "success": True,
            "data": tweet_dict
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweet/<tweet_id>/engagement')
def get_tweet_engagement(tweet_id: str):
    """获取推特互动率"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        engagement_rate = twitter_service.get_tweet_engagement_rate_sync(tweet_id)
        
        engagement_data = {
            "tweet_id": tweet_id,
            "engagement_rate": engagement_rate
        }
        
        return jsonify({
            "success": True,
            "data": engagement_data
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/user/<username>')
def get_user_info(username: str):
    """获取用户信息"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        user_data = twitter_service.get_user_info_sync(username)
        
        # Convert to dict for JSON serialization
        user_dict = {
            "user_id": user_data.user_id,
            "username": user_data.username,
            "name": user_data.name,
            "description": user_data.description,
            "public_metrics": user_data.public_metrics,
            "profile_image_url": user_data.profile_image_url,
            "verified": user_data.verified,
            "created_at": user_data.created_at
        }
        
        return jsonify({
            "success": True,
            "data": user_dict
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/user/<username>/tweets')
def get_user_tweets(username: str):
    """获取用户最近推特"""
    try:
        count = request.args.get('count', current_app.config['DEFAULT_TWEET_COUNT'], type=int)
        count = min(count, current_app.config['MAX_TWEETS_PER_REQUEST'])
        
        twitter_service = current_app.container.get('twitter_service')
        tweets_data = twitter_service.get_user_recent_tweets_with_metrics_sync(username, count)
        
        # Convert to list of dicts for JSON serialization
        tweets_list = [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in tweets_data
        ]
        
        return jsonify({
            "success": True,
            "data": {
                "username": username,
                "count": len(tweets_data),
                "tweets": tweets_list
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/search')
def search_tweets():
    """搜索推特"""
    try:
        query = request.args.get('q')
        if not query:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "Missing query parameter 'q'"
            }), 400
        
        count = request.args.get('count', current_app.config['DEFAULT_TWEET_COUNT'], type=int)
        count = min(count, current_app.config['MAX_TWEETS_PER_REQUEST'])
        
        twitter_service = current_app.container.get('twitter_service')
        search_results = twitter_service.search_tweets_sync(query, count)
        
        # Convert to list of dicts for JSON serialization
        results_list = [
            {
                "tweet_id": tweet.tweet_id,
                "text": tweet.text,
                "author_username": tweet.author_username,
                "author_name": tweet.author_name,
                "created_at": tweet.created_at,
                "public_metrics": tweet.public_metrics,
                "view_count": tweet.view_count,
                "url": tweet.url,
                "lang": tweet.lang,
                "engagement_rate": tweet.engagement_rate
            }
            for tweet in search_results
        ]
        
        return jsonify({
            "success": True,
            "data": {
                "query": query,
                "count": len(results_list),
                "tweets": results_list
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/tweets/views', methods=['POST'])
def batch_get_views():
    """批量获取推特浏览量"""
    try:
        data = request.get_json()
        if not data or 'tweet_ids' not in data:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "Tweet IDs array is required"
            }), 400
        
        tweet_ids = data['tweet_ids']
        if not isinstance(tweet_ids, list):
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": "Tweet IDs must be an array"
            }), 400
        
        if len(tweet_ids) > current_app.config['MAX_BATCH_SIZE']:
            return jsonify({
                "success": False,
                "error": "Invalid parameters",
                "message": f"Batch requests support maximum {current_app.config['MAX_BATCH_SIZE']} tweet IDs"
            }), 400
        
        twitter_service = current_app.container.get('twitter_service')
        views_data = twitter_service.batch_get_tweet_views_sync(tweet_ids)
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(views_data),
                "views": views_data
            }
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/data-sources/status')
def get_data_sources_status():
    """获取数据源状态"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        status = twitter_service.get_data_sources_status()
        
        return jsonify({
            "success": True,
            "data": status
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code


@bp.route('/data-sources/reset', methods=['POST'])
def reset_data_sources():
    """重置数据源状态"""
    try:
        twitter_service = current_app.container.get('twitter_service')
        twitter_service.reset_data_sources()
        
        return jsonify({
            "success": True,
            "message": "数据源状态已重置"
        })
        
    except Exception as e:
        response, status_code = handle_twitter_exception(e)
        return jsonify(response), status_code