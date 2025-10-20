"""
数据同步错误处理器

明确区分技术错误和内容错误，确保技术错误不会影响帖子状态
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging


class ErrorCategory(Enum):
    """错误分类"""
    TECHNICAL_ERROR = "technical"      # 技术错误：网络、服务器、浏览器等
    CONTENT_ERROR = "content"          # 内容错误：推文删除、私密、不存在等
    RATE_LIMIT = "rate_limit"          # 风控错误：需要等待重试
    UNKNOWN = "unknown"                # 未知错误


class ErrorAction(Enum):
    """错误处理动作"""
    SKIP_PRESERVE_STATUS = "skip_preserve"    # 跳过但保持帖子状态
    SKIP_MARK_INVALID = "skip_invalid"        # 跳过并标记帖子无效
    RETRY_WITH_WAIT = "retry_wait"            # 等待后重试
    FAIL_PROCESS = "fail"                     # 处理失败


@dataclass
class ErrorAnalysis:
    """错误分析结果"""
    category: ErrorCategory
    action: ErrorAction
    reason: str
    wait_time: Optional[int] = None  # 需要等待的秒数
    should_mark_invalid: bool = False
    log_level: str = "warning"


class SyncErrorHandler:
    """同步错误处理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 技术错误关键词
        self.technical_keywords = [
            'timeout', '超时', 'instance', '实例', 'browser', '浏览器',
            'network', '网络', 'connection', '连接', 'server', '服务器',
            'pool', '池', 'extraction', '提取', 'load_error', 'page_load'
        ]
        
        # 内容错误关键词
        self.content_keywords = [
            'tweet_not_found', 'tweet_protected', 'not_found', '不存在',
            'deleted', '删除', 'private', '私密', 'suspended', '暂停'
        ]
        
        # 风控错误关键词
        self.rate_limit_keywords = [
            'rate_limited', 'rate limit', '风控', 'login_required', 
            '登录', 'blocked', '阻止', 'restricted', '限制'
        ]
    
    def analyze_error(self, error: Exception, error_msg: str = "", 
                     detailed_reason: str = "", extraction_metadata: Dict[str, Any] = None) -> ErrorAnalysis:
        """
        分析错误并确定处理策略
        
        Args:
            error: 异常对象
            error_msg: 错误消息
            detailed_reason: 详细原因
            extraction_metadata: 提取元数据
            
        Returns:
            ErrorAnalysis: 错误分析结果
        """
        
        # 合并所有错误信息用于分析
        all_error_info = f"{str(error)} {error_msg} {detailed_reason}".lower()
        
        # 1. 检查是否是风控异常
        if (hasattr(error, 'wait_time') and 
            type(error).__name__ == 'RateLimitDetectedError'):
            return ErrorAnalysis(
                category=ErrorCategory.RATE_LIMIT,
                action=ErrorAction.RETRY_WITH_WAIT,
                reason=f"检测到风控，需等待 {error.wait_time} 秒",
                wait_time=error.wait_time,
                log_level="warning"
            )
        
        # 2. 检查风控关键词
        if any(keyword in all_error_info for keyword in self.rate_limit_keywords):
            return ErrorAnalysis(
                category=ErrorCategory.RATE_LIMIT,
                action=ErrorAction.RETRY_WITH_WAIT,
                reason=f"检测到风控相关错误: {detailed_reason or error_msg}",
                wait_time=300,  # 默认5分钟
                log_level="warning"
            )
        
        # 3. 检查内容错误（推文真正不存在）
        if any(keyword in all_error_info for keyword in self.content_keywords):
            return ErrorAnalysis(
                category=ErrorCategory.CONTENT_ERROR,
                action=ErrorAction.SKIP_MARK_INVALID,
                reason=f"推文内容问题: {detailed_reason or error_msg}",
                should_mark_invalid=True,
                log_level="info"
            )
        
        # 4. 检查技术错误
        if any(keyword in all_error_info for keyword in self.technical_keywords):
            return ErrorAnalysis(
                category=ErrorCategory.TECHNICAL_ERROR,
                action=ErrorAction.SKIP_PRESERVE_STATUS,
                reason=f"技术错误，不影响帖子状态: {detailed_reason or error_msg}",
                log_level="error"
            )
        
        # 5. 数据为空的情况（保守处理）
        if not error_msg and not detailed_reason:
            return ErrorAnalysis(
                category=ErrorCategory.TECHNICAL_ERROR,
                action=ErrorAction.SKIP_PRESERVE_STATUS,
                reason="数据提取为空，可能是技术问题",
                log_level="warning"
            )
        
        # 6. 未知错误（保守处理，不影响帖子状态）
        return ErrorAnalysis(
            category=ErrorCategory.UNKNOWN,
            action=ErrorAction.SKIP_PRESERVE_STATUS,
            reason=f"未知错误，保守跳过: {str(error)[:100]}",
            log_level="error"
        )
    
    def log_error_analysis(self, analysis: ErrorAnalysis, tweet_url: str):
        """记录错误分析结果"""
        
        # 根据分析结果选择日志级别和emoji
        if analysis.category == ErrorCategory.TECHNICAL_ERROR:
            emoji = "🔧"
            self.logger.error(f"{emoji} 技术错误 - {analysis.reason}: {tweet_url}")
        elif analysis.category == ErrorCategory.CONTENT_ERROR:
            emoji = "📝"
            self.logger.info(f"{emoji} 内容问题 - {analysis.reason}: {tweet_url}")
        elif analysis.category == ErrorCategory.RATE_LIMIT:
            emoji = "🚨"
            self.logger.warning(f"{emoji} 风控检测 - {analysis.reason}: {tweet_url}")
        else:
            emoji = "❓"
            self.logger.warning(f"{emoji} 未知错误 - {analysis.reason}: {tweet_url}")
    
    def should_mark_submission_invalid(self, analysis: ErrorAnalysis) -> bool:
        """判断是否应该标记submission为无效"""
        return analysis.should_mark_invalid
    
    def get_return_status(self, analysis: ErrorAnalysis) -> str:
        """获取应该返回的状态"""
        if analysis.action == ErrorAction.SKIP_PRESERVE_STATUS:
            return "skipped"
        elif analysis.action == ErrorAction.SKIP_MARK_INVALID:
            return "skipped"
        elif analysis.action == ErrorAction.RETRY_WITH_WAIT:
            return "retry_needed"
        else:
            return "failed"


# 全局实例
error_handler = SyncErrorHandler()