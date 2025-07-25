from flask import Blueprint

# 创建API蓝图
bp = Blueprint('api', __name__, url_prefix='/api/v1')

# 导入路由
from . import routes