"""
浏览器池监控API
提供浏览器池状态查看和管理功能
"""

import logging
from typing import Dict, Any, Optional
from flask import Blueprint, jsonify, request

from ..services.data_sources.playwright_pooled import PlaywrightPooledSource
from ..core.container import get_container


# 创建蓝图
pool_monitor_bp = Blueprint('pool_monitor', __name__, url_prefix='/api/pool')

logger = logging.getLogger(__name__)


def get_playwright_source() -> Optional[PlaywrightPooledSource]:
    """获取Playwright池化数据源"""
    try:
        container = get_container()
        playwright_source = container.get('playwright_source')
        if isinstance(playwright_source, PlaywrightPooledSource):
            return playwright_source
        return None
    except Exception as e:
        logger.error(f"获取Playwright数据源失败: {e}")
        return None


@pool_monitor_bp.route('/status', methods=['GET'])
async def get_pool_status():
    """获取浏览器池状态"""
    try:
        playwright_source = get_playwright_source()
        if not playwright_source:
            return jsonify({
                'error': 'Playwright池化数据源不可用',
                'status': 'unavailable'
            }), 503
        
        pool_status = await playwright_source.get_pool_status()
        
        return jsonify({
            'status': 'success',
            'data': pool_status,
            'timestamp': pool_status.get('timestamp')
        })
        
    except Exception as e:
        logger.error(f"获取池状态失败: {e}")
        return jsonify({
            'error': f'获取池状态失败: {str(e)}',
            'status': 'error'
        }), 500


@pool_monitor_bp.route('/metrics', methods=['GET'])
async def get_pool_metrics():
    """获取浏览器池指标摘要"""
    try:
        playwright_source = get_playwright_source()
        if not playwright_source:
            return jsonify({
                'error': 'Playwright池化数据源不可用',
                'status': 'unavailable'
            }), 503
        
        pool_status = await playwright_source.get_pool_status()
        
        # 提取关键指标
        pool_stats = pool_status.get('pool_stats', {})
        request_stats = pool_status.get('request_stats', {})
        
        metrics = {
            'pool_health': {
                'total_instances': pool_stats.get('total_instances', 0),
                'idle_instances': pool_stats.get('idle_instances', 0),
                'busy_instances': pool_stats.get('busy_instances', 0),
                'error_instances': pool_stats.get('error_instances', 0),
                'health_ratio': (pool_stats.get('total_instances', 0) - pool_stats.get('error_instances', 0)) / max(1, pool_stats.get('total_instances', 1))
            },
            'performance': {
                'total_requests': request_stats.get('total_requests', 0),
                'success_rate': request_stats.get('success_rate', 0.0),
                'pool_hit_rate': request_stats.get('pool_hit_rate', 0.0),
                'pool_hits': request_stats.get('pool_hits', 0),
                'pool_misses': request_stats.get('pool_misses', 0)
            },
            'pool_config': pool_status.get('pool_config', {}),
            'status': 'healthy' if pool_stats.get('error_instances', 0) == 0 else 'degraded'
        }
        
        return jsonify({
            'status': 'success',
            'data': metrics
        })
        
    except Exception as e:
        logger.error(f"获取池指标失败: {e}")
        return jsonify({
            'error': f'获取池指标失败: {str(e)}',
            'status': 'error'
        }), 500


@pool_monitor_bp.route('/instances', methods=['GET'])
async def get_instance_details():
    """获取浏览器实例详细信息"""
    try:
        playwright_source = get_playwright_source()
        if not playwright_source:
            return jsonify({
                'error': 'Playwright池化数据源不可用',
                'status': 'unavailable'
            }), 503
        
        pool_status = await playwright_source.get_pool_status()
        instances = pool_status.get('instances', [])
        
        # 添加一些统计信息
        instance_summary = {
            'total_count': len(instances),
            'by_status': {},
            'instances': instances
        }
        
        # 按状态分组统计
        for instance in instances:
            status = instance.get('status', 'unknown')
            instance_summary['by_status'][status] = instance_summary['by_status'].get(status, 0) + 1
        
        return jsonify({
            'status': 'success',
            'data': instance_summary
        })
        
    except Exception as e:
        logger.error(f"获取实例详情失败: {e}")
        return jsonify({
            'error': f'获取实例详情失败: {str(e)}',
            'status': 'error'
        }), 500


@pool_monitor_bp.route('/health', methods=['GET'])
async def health_check():
    """简单的健康检查端点"""
    try:
        playwright_source = get_playwright_source()
        if not playwright_source:
            return jsonify({
                'status': 'unhealthy',
                'message': 'Playwright池化数据源不可用'
            }), 503
        
        pool_status = await playwright_source.get_pool_status()
        
        if not pool_status.get('initialized', False):
            return jsonify({
                'status': 'unhealthy',
                'message': '浏览器池未初始化'
            }), 503
        
        pool_stats = pool_status.get('pool_stats', {})
        total_instances = pool_stats.get('total_instances', 0)
        error_instances = pool_stats.get('error_instances', 0)
        
        if total_instances == 0:
            return jsonify({
                'status': 'unhealthy',
                'message': '没有可用的浏览器实例'
            }), 503
        
        if error_instances >= total_instances:
            return jsonify({
                'status': 'unhealthy',
                'message': '所有浏览器实例都处于错误状态'
            }), 503
        
        health_ratio = (total_instances - error_instances) / total_instances
        status = 'healthy' if health_ratio >= 0.8 else 'degraded'
        
        return jsonify({
            'status': status,
            'message': f'浏览器池运行正常，健康度: {health_ratio:.1%}',
            'health_ratio': health_ratio,
            'total_instances': total_instances,
            'healthy_instances': total_instances - error_instances
        })
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'健康检查失败: {str(e)}'
        }), 500


# 为了兼容现有代码，也提供一个类
class PoolMonitorAPI:
    """浏览器池监控API类（兼容现有代码）"""
    
    def __init__(self, browser_pool=None):
        self.browser_pool = browser_pool
        self.logger = logging.getLogger(__name__)
    
    async def get_status(self) -> Dict[str, Any]:
        """获取池状态"""
        if self.browser_pool:
            return await self.browser_pool.get_pool_status()
        return {'error': '浏览器池不可用'}
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取关键指标"""
        status = await self.get_status()
        if 'error' in status:
            return status
        
        pool_stats = status.get('pool_stats', {})
        request_stats = status.get('request_stats', {})
        
        return {
            'instances': {
                'total': pool_stats.get('total_instances', 0),
                'idle': pool_stats.get('idle_instances', 0),
                'busy': pool_stats.get('busy_instances', 0),
                'error': pool_stats.get('error_instances', 0)
            },
            'requests': {
                'total': request_stats.get('total_requests', 0),
                'success_rate': request_stats.get('success_rate', 0.0),
                'pool_hit_rate': request_stats.get('pool_hit_rate', 0.0)
            }
        }