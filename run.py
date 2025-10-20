#!/usr/bin/env python3
"""
Flask应用启动入口
"""

import os
import sys

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import create_app
from app.config import get_config

# 获取环境
env = os.getenv('FLASK_ENV', 'development')

# 创建应用
app = create_app(env)

# 验证配置
try:
    config_class = get_config(env)
    config_class.validate()
except ValueError as e:
    print(f"❌ 配置错误: {e}")
    print("请设置 TWITTER_BEARER_TOKEN 环境变量或使用 .env.example 创建 .env 文件")
    exit(1)

if __name__ == '__main__':
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 5000)
    
    print(f"🚀 启动TW Analytics API服务 [{env}]")
    print(f"📡 服务地址: http://{host}:{port}")
    print(f"📋 健康检查: http://{host}:{port}/api/v1/health")
    print("=" * 50)
    
    app.run(
        host=host,
        port=port,
        debug=app.config.get('DEBUG', False)
    )