"""
Gunicorn配置文件
"""

import os

# 服务器配置
bind = f"0.0.0.0:{os.getenv('PORT', '5100')}"
workers = int(os.getenv('WORKERS', '2'))
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# 日志配置
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()

# 进程配置
preload_app = True
max_requests = 1000
max_requests_jitter = 50

# 安全配置
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190