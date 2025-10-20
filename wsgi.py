#!/usr/bin/env python3
"""
生产环境WSGI入口点
"""

import os
import sys

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import create_app

# 创建应用实例
application = create_app(os.getenv('FLASK_ENV', 'production'))

# Gunicorn兼容
app = application

if __name__ == '__main__':
    # 直接运行时使用Waitress
    from waitress import serve
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5100))
    
    print(f"🚀 启动TW Analytics API服务")
    print(f"📡 http://{host}:{port}")
    
    serve(application, host=host, port=port, threads=4)