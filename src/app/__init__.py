"""
Flask应用工厂模式 - 集成依赖注入
"""

import os
import logging
from flask import Flask
from flask_cors import CORS

from .config import get_config
from .api import bp as api_bp
from .api.comprehensive import comprehensive_bp
from .api.view_booster import view_booster_bp
# from .api.cookie_status import cookie_status_bp  # 已移除cookie系统
from .core import get_app_container, TwitterServiceProvider, FlaskIntegrationProvider


def create_app(config_name=None):
    """Flask应用工厂函数"""
    
    app = Flask(__name__, instance_relative_config=True)
    
    # 加载配置
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    config = get_config(config_name)
    app.config.from_object(config)
    
    # 设置JSON不转义中文字符
    app.config['JSON_AS_ASCII'] = False
    
    # 配置CORS
    CORS(app)
    
    # 初始化依赖注入容器
    container = get_app_container()
    
    # 注册服务提供者
    TwitterServiceProvider().register(container)
    FlaskIntegrationProvider(app).register(container)
    
    # 将容器存储到Flask应用中
    app.container = container
    
    # 配置日志 - 总是配置日志，包括调试模式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # 输出到控制台
        ]
    )
    
    # 确保实例文件夹存在
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # 注册蓝图
    app.register_blueprint(api_bp)
    app.register_blueprint(comprehensive_bp)
    app.register_blueprint(view_booster_bp)
    # app.register_blueprint(cookie_status_bp)  # 已移除cookie系统
    
    # 根路由
    @app.route('/')
    def index():
        return {
            "message": "Twitter data extraction API service",
            "version": "2.0.0",
            "health_check": "/api/v1/health",
            "comprehensive_extraction": "/api/tweet/comprehensive",
            "auth_status": "/api/v1/auth/status",
            "cookie_refresh": "/api/v1/auth/refresh",
            "view_booster": "/api/v1/view-booster"
        }
    
    # 全局错误处理
    @app.errorhandler(404)
    def not_found(_):
        return {"success": False, "error": "Endpoint not found"}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server error: {error}')
        return {"success": False, "error": "Internal server error"}, 500
    
    # 浏览器池采用延迟初始化策略，在首次请求时自动创建
    
    return app