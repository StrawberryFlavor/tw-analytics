"""
数据模型类

遵循SOLID原则，定义数据库表的结构模型
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json


@dataclass
class CampaignTweetSnapshot:
    """campaign_tweet_snapshot 表的数据模型 - 单一职责原则"""
    
    # 基础字段
    id: Optional[int] = None
    success: bool = False
    message: Optional[str] = None
    
    # 推文基本信息
    tweet_id: str = ""
    tweet_text: Optional[str] = None
    tweet_time_utc: Optional[datetime] = None
    tweet_type: Optional[str] = None
    
    # 作者信息
    author_username: str = ""
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    author_verified: bool = False
    
    # 推文指标
    views: Optional[int] = None
    replies: Optional[int] = None
    retweets: Optional[int] = None
    likes: Optional[int] = None
    quotes: Optional[int] = None
    
    # 汇总信息
    summary_total_tweets: Optional[int] = None
    summary_has_thread: Optional[bool] = None
    summary_has_replies: Optional[bool] = None
    
    # JSON字段（复杂数据结构）
    primary_tweet: Optional[Dict[str, Any]] = None
    thread: Optional[List[Dict[str, Any]]] = None
    related: Optional[List[Dict[str, Any]]] = None
    
    # 虚拟字段（计算字段）
    thread_count: Optional[int] = None
    related_count: Optional[int] = None
    
    # 时间戳
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CampaignTweetSnapshot':
        """从字典创建实例 - 工厂方法模式"""
        # 处理JSON字段
        primary_tweet = data.get('primary_tweet')
        if isinstance(primary_tweet, str):
            try:
                primary_tweet = json.loads(primary_tweet)
            except json.JSONDecodeError:
                primary_tweet = None
        
        thread = data.get('thread')
        if isinstance(thread, str):
            try:
                thread = json.loads(thread)
            except json.JSONDecodeError:
                thread = None
        
        related = data.get('related')
        if isinstance(related, str):
            try:
                related = json.loads(related)
            except json.JSONDecodeError:
                related = None
        
        return cls(
            id=data.get('id'),
            success=bool(data.get('success', False)),
            message=data.get('message'),
            tweet_id=data.get('tweet_id', ''),
            tweet_text=data.get('tweet_text'),
            tweet_time_utc=data.get('tweet_time_utc'),
            tweet_type=data.get('tweet_type'),
            author_username=data.get('author_username', ''),
            author_name=data.get('author_name'),
            author_avatar=data.get('author_avatar'),
            author_verified=bool(data.get('author_verified', False)),
            views=data.get('views'),
            replies=data.get('replies'),
            retweets=data.get('retweets'),
            likes=data.get('likes'),
            quotes=data.get('quotes'),
            summary_total_tweets=data.get('summary_total_tweets'),
            summary_has_thread=bool(data.get('summary_has_thread')) if data.get('summary_has_thread') is not None else None,
            summary_has_replies=bool(data.get('summary_has_replies')) if data.get('summary_has_replies') is not None else None,
            primary_tweet=primary_tweet,
            thread=thread,
            related=related,
            thread_count=data.get('thread_count'),
            related_count=data.get('related_count'),
            created_at=data.get('created_at')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 - 用于数据库插入/更新"""
        result = {}
        
        # 基础字段
        if self.id is not None:
            result['id'] = self.id
        result['success'] = self.success
        if self.message is not None:
            result['message'] = self.message
        
        # 推文信息
        result['tweet_id'] = self.tweet_id
        if self.tweet_text is not None:
            result['tweet_text'] = self.tweet_text
        if self.tweet_time_utc is not None:
            result['tweet_time_utc'] = self.tweet_time_utc
        if self.tweet_type is not None:
            result['tweet_type'] = self.tweet_type
        
        # 作者信息
        result['author_username'] = self.author_username
        if self.author_name is not None:
            result['author_name'] = self.author_name
        if self.author_avatar is not None:
            result['author_avatar'] = self.author_avatar
        result['author_verified'] = self.author_verified
        
        # 推文指标
        if self.views is not None:
            result['views'] = self.views
        if self.replies is not None:
            result['replies'] = self.replies
        if self.retweets is not None:
            result['retweets'] = self.retweets
        if self.likes is not None:
            result['likes'] = self.likes
        if self.quotes is not None:
            result['quotes'] = self.quotes
        
        # 汇总信息
        if self.summary_total_tweets is not None:
            result['summary_total_tweets'] = self.summary_total_tweets
        if self.summary_has_thread is not None:
            result['summary_has_thread'] = self.summary_has_thread
        if self.summary_has_replies is not None:
            result['summary_has_replies'] = self.summary_has_replies
        
        # JSON字段
        if self.primary_tweet is not None:
            result['primary_tweet'] = json.dumps(self.primary_tweet, ensure_ascii=False)
        if self.thread is not None:
            result['thread'] = json.dumps(self.thread, ensure_ascii=False)
        if self.related is not None:
            result['related'] = json.dumps(self.related, ensure_ascii=False)
        
        # 不包含虚拟字段（thread_count, related_count）因为它们是计算字段
        # created_at 由数据库自动管理
        
        return result
    
    def get_insert_query(self) -> tuple[str, tuple]:
        """获取插入查询语句和参数 - 依赖倒置原则"""
        data = self.to_dict()
        
        # 排除id和created_at（自动生成）
        data.pop('id', None)
        data.pop('created_at', None)
        
        columns = list(data.keys())
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)
        
        query = f"INSERT INTO campaign_tweet_snapshot ({column_names}) VALUES ({placeholders})"
        values = tuple(data[col] for col in columns)
        
        return query, values
    
    def get_update_query(self, where_clause: str = "id = %s") -> tuple[str, tuple]:
        """获取更新查询语句和参数"""
        data = self.to_dict()
        
        # 排除id和created_at（不允许更新）
        record_id = data.pop('id', None)
        data.pop('created_at', None)
        
        if not data:
            raise ValueError("没有需要更新的字段")
        
        set_clauses = []
        values = []
        
        for column, value in data.items():
            set_clauses.append(f"{column} = %s")
            values.append(value)
        
        query = f"UPDATE campaign_tweet_snapshot SET {', '.join(set_clauses)} WHERE {where_clause}"
        
        # 如果使用默认的where子句，添加id参数
        if where_clause == "id = %s" and record_id is not None:
            values.append(record_id)
        
        return query, tuple(values)
    
    def is_valid(self) -> tuple[bool, str]:
        """验证数据有效性 - 开闭原则（可扩展验证规则）"""
        if not self.tweet_id:
            return False, "tweet_id 不能为空"
        
        if not self.author_username:
            return False, "author_username 不能为空"
        
        if len(self.tweet_id) > 64:
            return False, "tweet_id 长度不能超过64字符"
        
        if len(self.author_username) > 100:
            return False, "author_username 长度不能超过100字符"
        
        if self.message and len(self.message) > 500:
            return False, "message 长度不能超过500字符"
        
        if self.author_name and len(self.author_name) > 200:
            return False, "author_name 长度不能超过200字符"
        
        if self.author_avatar and len(self.author_avatar) > 500:
            return False, "author_avatar 长度不能超过500字符"
        
        if self.tweet_type and len(self.tweet_type) > 50:
            return False, "tweet_type 长度不能超过50字符"
        
        return True, ""
    
    def __repr__(self) -> str:
        return (f"CampaignTweetSnapshot(id={self.id}, tweet_id='{self.tweet_id}', "
                f"author_username='{self.author_username}', success={self.success})")


class CampaignTweetSnapshotQuery:
    """查询构建器 - 单一职责原则，专门负责构建查询语句"""
    
    def __init__(self):
        self._select_fields = []
        self._where_conditions = []
        self._order_by = []
        self._limit_count = None
        self._offset_count = None
        self._params = []
    
    def select(self, *fields: str) -> 'CampaignTweetSnapshotQuery':
        """选择字段"""
        self._select_fields.extend(fields)
        return self
    
    def where(self, condition: str, *params) -> 'CampaignTweetSnapshotQuery':
        """添加WHERE条件"""
        self._where_conditions.append(condition)
        self._params.extend(params)
        return self
    
    def where_tweet_id(self, tweet_id: str) -> 'CampaignTweetSnapshotQuery':
        """按tweet_id查询"""
        return self.where("tweet_id = %s", tweet_id)
    
    def where_author(self, author_username: str) -> 'CampaignTweetSnapshotQuery':
        """按作者查询"""
        return self.where("author_username = %s", author_username)
    
    def where_success(self, success: bool = True) -> 'CampaignTweetSnapshotQuery':
        """按成功状态查询"""
        return self.where("success = %s", success)
    
    def where_time_range(self, start_time: datetime, end_time: datetime) -> 'CampaignTweetSnapshotQuery':
        """按时间范围查询"""
        return self.where("tweet_time_utc BETWEEN %s AND %s", start_time, end_time)
    
    def order_by(self, field: str, direction: str = "ASC") -> 'CampaignTweetSnapshotQuery':
        """添加排序"""
        self._order_by.append(f"{field} {direction}")
        return self
    
    def limit(self, count: int, offset: int = 0) -> 'CampaignTweetSnapshotQuery':
        """限制结果数量"""
        self._limit_count = count
        self._offset_count = offset
        return self
    
    def build(self) -> tuple[str, tuple]:
        """构建查询语句"""
        # SELECT部分
        if self._select_fields:
            select_clause = f"SELECT {', '.join(self._select_fields)}"
        else:
            select_clause = "SELECT *"
        
        # FROM部分
        from_clause = "FROM campaign_tweet_snapshot"
        
        # WHERE部分
        where_clause = ""
        if self._where_conditions:
            where_clause = f"WHERE {' AND '.join(self._where_conditions)}"
        
        # ORDER BY部分
        order_clause = ""
        if self._order_by:
            order_clause = f"ORDER BY {', '.join(self._order_by)}"
        
        # LIMIT部分
        limit_clause = ""
        if self._limit_count is not None:
            if self._offset_count and self._offset_count > 0:
                limit_clause = f"LIMIT {self._offset_count}, {self._limit_count}"
            else:
                limit_clause = f"LIMIT {self._limit_count}"
        
        # 组合查询
        query_parts = [select_clause, from_clause]
        if where_clause:
            query_parts.append(where_clause)
        if order_clause:
            query_parts.append(order_clause)
        if limit_clause:
            query_parts.append(limit_clause)
        
        query = " ".join(query_parts)
        return query, tuple(self._params)