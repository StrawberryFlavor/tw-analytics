# API 返回数据结构文档

本文档详细说明了 TW Analytics API 的统一返回数据结构，采用action_info设计，支持四种推文类型。

## 目录
- [API概览](#api概览)
- [基础响应结构](#基础响应结构)
- [推文分类系统](#推文分类系统)
- [推文类型详解](#推文类型详解)
- [数据字段说明](#数据字段说明)
- [解析指南](#解析指南)
- [示例代码](#示例代码)

## API概览

### 主要端点
```http
POST /api/tweet/comprehensive
Content-Type: application/json

{
  "url": "https://x.com/username/status/1234567890"
}
```

### 返回格式
所有API返回统一的JSON格式，包含成功状态、数据和消息字段。

## 基础响应结构

```json
{
  "success": true,
  "data": {
    "user_tweet": {},     // URL指定的用户推文（用户动作）
    "primary_tweet": {},  // 页面主推文（被操作的推文）
    "thread": [],         // 线程推文数组
    "related": [],        // 相关推文数组
    "summary": {}         // 统计信息
  },
  "message": "Comprehensive data extraction completed"
}
```

## 双字段架构设计

系统采用user_tweet + primary_tweet双字段架构：

### 1. User Tweet
- **定义**: URL指定的用户推文，表示用户的动作
- **内容**: 用户发布的内容（原创/引用评论/转发评论/回复）
- **位置**: `data.user_tweet`
- **说明**: 包含用户的实际操作和文本内容

### 2. Primary Tweet  
- **定义**: 页面主推文，被用户操作的目标推文
- **内容**: 被引用/转发/回复的原始推文
- **位置**: `data.primary_tweet`
- **说明**: 
  - 原创推文时为`null`（避免冗余）
  - 非原创推文时包含被操作的完整推文数据

### 3. Action Info 统一设计
- **定义**: 统一的操作信息结构
- **位置**: `data.user_tweet.action_info`
- **说明**: 引用、转发、回复使用相同的target结构

## 推文类型详解

### 原创推文 (Original Tweet)

用户发布的原创内容，结构简洁。

```json
{
  "user_tweet": {
    "id": "1234567890",
    "text": "这是一条原创推文内容",
    "author": {
      "username": "example_user",
      "name": "示例用户",
      "avatar": "https://pbs.twimg.com/profile_images/...",
      "verified": false
    },
    "time": "2024-01-15T10:30:00Z",
    "type": "original",
    "metrics": {
      "likes": 100,
      "retweets": 50,
      "replies": 25,
      "quotes": 10,
      "views": 5000
    }
    // 无action_info - 原创推文无需额外操作信息
  },
  "primary_tweet": null  // 原创推文没有主推文，避免数据冗余
}
```

### 引用推文 (Quote Tweet)

用户引用其他推文并添加评论，使用统一的action_info结构。

```json
{
  "user_tweet": {
    "id": "9876543210_quote",
    "text": "用户的引用评论",  // 用户添加的评论
    "author": {
      "username": "quote_user",
      "name": "引用用户",
      "verified": false
    },
    "time": "2024-01-15T09:00:00Z",
    "type": "quote",
    "metrics": {
      "likes": 25,
      "retweets": 5,
      "replies": 10,
      "quotes": 2,
      "views": 500
    },
    "action_info": {
      "target": {
        "author": "original_author",
        "text": "被引用的原始推文内容",
        "url": "https://x.com/original_author/status/9876543210",
        "id": "9876543210"
      }
    }
  },
  "primary_tweet": {
    "id": "9876543210",
    "text": "被引用的原始推文内容",  // 完整的原始推文
    "author": {
      "username": "original_author",
      "name": "原作者",
      "verified": true
    },
    "time": "2024-01-14T15:20:00Z",
    "type": "original",
    "metrics": {
      "likes": 200,  // 真实的原推文数据
      "retweets": 80,
      "replies": 40,
      "quotes": 20,
      "views": 8000
    }
  }
}
```

### 转发推文 (Retweet)

用户转发其他推文的内容。

```json
{
  "id": "5555555555",
  "text": "被转发的推文内容",
  "author": {
    "username": "original_author",
    "name": "原作者",
    "avatar": "https://pbs.twimg.com/profile_images/...",
    "verified": true
  },
  "time": "2024-01-15T11:00:00Z",
  "type": "retweet",
  "quality_score": "medium",
  "action": {
    "type": "retweet",
    "user": {
      "username": "retweeter",
      "name": "转发用户",
      "avatar": "https://pbs.twimg.com/profile_images/...",
      "verified": false
    },
    "comment": "转发时的评论（如果有）",
    "timestamp": "2024-01-15T11:00:00Z",
    "retweeted_by": "retweeter"
  },
  "metrics": {
    "likes": 150,
    "retweets": 60,
    "replies": 30,
    "quotes": 15,
    "views": 6000
  }
}
```

### 回复推文 (Reply Tweet)

对其他推文的回复。

```json
{
  "id": "7777777777",
  "text": "这是一条回复内容",
  "author": {
    "username": "replier",
    "name": "回复用户",
    "avatar": "https://pbs.twimg.com/profile_images/...",
    "verified": false
  },
  "time": "2024-01-15T12:00:00Z",
  "type": "reply",
  "quality_score": "low",
  "action": {
    "type": "reply",
    "user": {
      "username": "replier",
      "name": "回复用户",
      "avatar": "https://pbs.twimg.com/profile_images/...",
      "verified": false
    },
    "timestamp": "2024-01-15T12:00:00Z"
  },
  "reply_context": {
    "replying_to_text": "正在回复的推文内容片段",
    "replying_to_users": ["@original_author"],
    "original_tweet_id": "9876543210",
    "original_tweet_link": {
      "url": "https://x.com/original_author/status/9876543210",
      "text": "View original tweet",
      "type": "tweet"
    }
  },
  "metrics": {
    "likes": 10,
    "retweets": 2,
    "replies": 5,
    "quotes": 0,
    "views": 500
  }
}
```

### 线程推文 (Thread Tweet)

同一作者发布的连续推文。

```json
{
  "id": "8888888888",
  "text": "这是线程的第二条推文 2/",
  "author": {
    "username": "thread_author",
    "name": "线程作者",
    "avatar": "https://pbs.twimg.com/profile_images/...",
    "verified": false
  },
  "time": "2024-01-15T10:35:00Z",
  "type": "thread",
  "quality_score": "medium",
  "metrics": {
    "likes": 75,
    "retweets": 25,
    "replies": 15,
    "quotes": 5,
    "views": 3000
  }
}
```

## 数据字段说明

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 推文唯一标识符 |
| `text` | string | 推文文本内容 |
| `author` | object | 作者信息对象 |
| `time` | string | 发布时间 (ISO 8601格式) |
| `type` | string | 推文类型标识 |
| `quality_score` | string | 内容质量评分 (`high`/`medium`/`low`) |
| `metrics` | object | 互动数据对象 |

### 作者信息字段 (author)

| 字段 | 类型 | 说明 |
|------|------|------|
| `username` | string | 用户名（不含@符号） |
| `name` | string | 显示名称 |
| `avatar` | string | 头像URL |
| `verified` | boolean | 是否为认证用户 |

### 互动数据字段 (metrics)

| 字段 | 类型 | 说明 |
|------|------|------|
| `likes` | number | 点赞数 |
| `retweets` | number | 转发数 |
| `replies` | number | 回复数 |
| `quotes` | number | 引用数 |
| `views` | number | 浏览数 |

### 媒体字段 (media)

```json
{
  "type": "photo|video|gif",
  "url": "媒体文件URL",
  "alt": "替代文本",
  "width": 1200,
  "height": 800
}
```

### 链接字段 (links)

```json
{
  "url": "链接URL",
  "text": "链接显示文本",
  "type": "external|tweet"
}
```

### 操作信息字段 (action)

用于描述引用、转发、回复等操作的详细信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 操作类型 (`quote`/`retweet`/`reply`) |
| `user` | object | 执行操作的用户信息 |
| `comment` | string | 操作时的评论（可选） |
| `timestamp` | string | 操作时间 |

## 解析指南

### 1. 推文类型判断

```javascript
function getTweetType(tweet) {
  // 检查是否有操作信息
  if (tweet.action) {
    return tweet.action.type; // "quote", "retweet", "reply"
  }
  
  // 检查类型字段
  if (tweet.type === "original") {
    return "original";
  } else if (tweet.type === "thread") {
    return "thread";
  }
  
  return "unknown";
}
```

### 2. 获取实际内容作者

```javascript
function getContentAuthor(tweet) {
  // 对于统一格式的推文，author字段就是内容的实际作者
  // 操作用户信息在action.user中
  return tweet.author;
}

function getActionUser(tweet) {
  // 获取执行引用、转发等操作的用户
  return tweet.action ? tweet.action.user : null;
}
```

### 3. 内容质量评估

```javascript
function isHighQualityContent(tweet) {
  return tweet.quality_score === "high";
}

function hasMedia(tweet) {
  return tweet.media && tweet.media.length > 0;
}

function hasExternalLinks(tweet) {
  return tweet.links && tweet.links.some(link => link.type === "external");
}
```

### 4. 处理不同推文类型

```javascript
function processTweet(tweet) {
  const type = getTweetType(tweet);
  
  switch(type) {
    case "original":
      return processOriginalTweet(tweet);
    
    case "quote":
      return processQuoteTweet(tweet);
    
    case "retweet":
      return processRetweetTweet(tweet);
    
    case "reply":
      return processReplyTweet(tweet);
    
    case "thread":
      return processThreadTweet(tweet);
    
    default:
      return processGenericTweet(tweet);
  }
}

function processQuoteTweet(tweet) {
  return {
    // 主要内容是被引用的推文
    originalContent: {
      text: tweet.text,
      author: tweet.author,
      metrics: tweet.metrics
    },
    // 引用操作信息
    quoteAction: {
      user: tweet.action.user,
      comment: tweet.action.comment,
      time: tweet.action.timestamp
    }
  };
}
```

## 示例代码

### JavaScript 解析示例

```javascript
// 解析API响应
function parseApiResponse(response) {
  if (!response.success) {
    throw new Error(`API Error: ${response.message}`);
  }
  
  const data = response.data;
  
  return {
    primaryTweet: parseTweet(data.tweet),
    threadTweets: data.thread.map(parseTweet),
    relatedTweets: data.related.map(parseTweet),
    context: data.context,
    metadata: data.meta
  };
}

function parseTweet(tweet) {
  if (!tweet) return null;
  
  const parsed = {
    id: tweet.id,
    content: tweet.text,
    author: tweet.author,
    publishTime: new Date(tweet.time),
    type: getTweetType(tweet),
    qualityScore: tweet.quality_score,
    engagement: {
      likes: tweet.metrics.likes || 0,
      retweets: tweet.metrics.retweets || 0,
      replies: tweet.metrics.replies || 0,
      quotes: tweet.metrics.quotes || 0,
      views: tweet.metrics.views || 0
    },
    hasMedia: tweet.media && tweet.media.length > 0,
    hasLinks: tweet.links && tweet.links.length > 0
  };
  
  // 处理操作信息
  if (tweet.action) {
    parsed.actionInfo = {
      type: tweet.action.type,
      user: tweet.action.user,
      comment: tweet.action.comment,
      timestamp: new Date(tweet.action.timestamp)
    };
  }
  
  return parsed;
}
```

### Python 解析示例

```python
from datetime import datetime
from typing import Dict, List, Optional

def parse_api_response(response: Dict) -> Dict:
    """解析API响应"""
    if not response.get('success'):
        raise ValueError(f"API Error: {response.get('message')}")
    
    data = response['data']
    
    return {
        'primary_tweet': parse_tweet(data.get('tweet')),
        'thread_tweets': [parse_tweet(t) for t in data.get('thread', [])],
        'related_tweets': [parse_tweet(t) for t in data.get('related', [])],
        'context': data.get('context', {}),
        'metadata': data.get('meta', {})
    }

def parse_tweet(tweet: Optional[Dict]) -> Optional[Dict]:
    """解析单个推文"""
    if not tweet:
        return None
    
    parsed = {
        'id': tweet.get('id'),
        'content': tweet.get('text'),
        'author': tweet.get('author', {}),
        'publish_time': datetime.fromisoformat(tweet.get('time', '').replace('Z', '+00:00')),
        'type': get_tweet_type(tweet),
        'quality_score': tweet.get('quality_score'),
        'engagement': {
            'likes': tweet.get('metrics', {}).get('likes', 0),
            'retweets': tweet.get('metrics', {}).get('retweets', 0),
            'replies': tweet.get('metrics', {}).get('replies', 0),
            'quotes': tweet.get('metrics', {}).get('quotes', 0),
            'views': tweet.get('metrics', {}).get('views', 0)
        },
        'has_media': bool(tweet.get('media')),
        'has_links': bool(tweet.get('links'))
    }
    
    # 处理操作信息
    if tweet.get('action'):
        action = tweet['action']
        parsed['action_info'] = {
            'type': action.get('type'),
            'user': action.get('user', {}),
            'comment': action.get('comment'),
            'timestamp': datetime.fromisoformat(action.get('timestamp', '').replace('Z', '+00:00'))
        }
    
    return parsed

def get_tweet_type(tweet: Dict) -> str:
    """获取推文类型"""
    if tweet.get('action'):
        return tweet['action']['type']
    
    tweet_type = tweet.get('type', '')
    if tweet_type == 'original':
        return 'original'
    elif tweet_type == 'thread':
        return 'thread'
    
    return 'unknown'
```

## 数据一致性保证

### 字段唯一性
系统确保每个推文对象中的字段都是唯一的，不会出现重复字段。特别是：

- **`type` 字段**：每个推文只有一个明确的类型标识
- **字段覆盖**：后续处理不会意外覆盖已设置的字段值
- **数据完整性**：所有字段都经过统一的清理和验证流程

### 类型字段说明
```javascript
// 正确的类型字段值示例
{
  "type": "original",     // 原创推文
  "type": "quote",        // 引用推文
  "type": "retweet",      // 转发推文
  "type": "reply",        // 回复推文
  "type": "thread"        // 线程推文
}
```

**注意**: 引用、转发、回复类型的推文使用"统一内容逻辑"，主要内容是被操作的原始推文，操作信息在 `action` 字段中。

## 最佳实践

### 1. 数据验证
- 始终检查 `success` 字段
- 验证必需字段是否存在
- 处理可能为空的数组和对象

### 2. 类型处理
- 优先使用 `action` 字段判断推文操作类型
- 理解"统一内容逻辑"：主要内容是用户最关心的
- 使用 `action` 字段获取操作详情

### 3. 性能优化
- 根据 `quality_score` 筛选高质量内容
- 缓存解析结果避免重复处理

### 4. 错误处理
- 捕获日期解析异常
- 处理缺失的媒体或链接数据
- 提供回退机制

## 更新日志

- **v1.0** (2024-01): 初始版本，基础推文类型支持
- **v2.0** (2024-07): 引入统一内容逻辑和质量评分系统
- **v2.1** (2024-07): 添加线程检测和改进的分类算法
- **v2.2** (2024-07): 修复字段重复问题，确保数据一致性
- **v3.0** (2024-07): 简化API，移除向后兼容字段，支持Simple/Full两种模式

---

如有疑问或需要更多示例，请参考项目的 README.md 或提交 Issue。