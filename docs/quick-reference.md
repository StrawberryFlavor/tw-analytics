# API 快速参考

## 基础请求

```bash
curl -X POST http://localhost:5100/api/tweet/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/username/status/1234567890"}'
```

## 响应结构概览

```json
{
  "success": true,
  "data": {
    "user_tweet": {},     // URL指定的用户推文（用户动作）
    "primary_tweet": {},  // 页面主推文（被操作的推文，原创时为null）
    "thread": [],         // 线程推文
    "related": [],        // 相关推文
    "summary": {}         // 统计信息
  }
}
```

## 推文类型快速识别

| 字段检查 | 推文类型 | action_info | primary_tweet |
|----------|----------|-------------|---------------|
| `type: "original"` | 原创推文 | 无 | null |
| `type: "quote"` | 引用推文 | 有 target | 被引用推文 |
| `type: "retweet"` | 转发推文 | 有 target | 被转发推文 |
| `type: "reply"` | 回复推文 | 有 target | 被回复推文 |

**核心原则**: action_info.target统一描述操作目标，消除数据冗余。

## 关键字段速查

### 必有字段
```json
{
  "id": "推文ID",
  "text": "推文内容",
  "author": {
    "username": "用户名",
    "name": "显示名",
    "verified": false
  },
  "time": "2024-01-15T10:30:00Z",
  "metrics": {
    "likes": 100,
    "retweets": 50,
    "replies": 25
  }
}
```

### action_info统一结构 (非原创推文时存在)
```json
{
  "action_info": {
    "target": {
      "author": "目标用户名",
      "text": "目标推文内容",
      "url": "目标推文链接",  // 仅引用推文有
      "id": "目标推文ID"
    }
  }
}
```

## 解析代码片段

### JavaScript
```javascript
// 获取推文类型（直接从type字段）
const type = tweet.type;

// 判断是否为操作类型（引用/转发/回复）
const isActionType = type.endsWith('_unified');

// 获取内容作者（实际内容的作者）
const contentAuthor = tweet.author;

// 获取操作用户（引用/转发的用户）
const actionUser = tweet.action?.user;

// 检查是否高质量内容
const isHighQuality = tweet.quality_score === "high";
```

### Python
```python
# 获取推文类型（直接从type字段）
tweet_type = tweet.get('type')

# 判断是否为操作类型（引用/转发/回复）
is_action_type = tweet_type.endswith('_unified') if tweet_type else False

# 获取内容作者
content_author = tweet.get('author', {})

# 获取操作用户
action_user = tweet.get('action', {}).get('user')

# 检查是否高质量内容
is_high_quality = tweet.get('quality_score') == 'high'
```

## 常见问题

**Q: 为什么引用推文的 `type` 是 `quote_unified` 而不是 `quote`？**
A: `_unified` 后缀表示使用了统一内容逻辑，确保数据结构一致性，避免字段重复或冲突。

**Q: 为什么引用推文的 `author` 不是引用用户？**
A: 系统采用"统一内容逻辑"，`author` 是内容的实际作者，引用用户信息在 `action.user` 中。

**Q: 如何区分主推文和线程推文？**
A: 主推文在 `data.tweet`，线程推文在 `data.thread[]` 数组中。

**Q: `quality_score` 是如何计算的？**
A: 基于文本长度、互动数据、媒体内容等因素综合评分，分为 `high`/`medium`/`low`。

## 错误处理

```json
{
  "success": false,
  "error": "错误类型",
  "message": "详细错误信息"
}
```

常见错误：
- `Invalid parameters`: 参数错误
- `Data source error`: 数据提取失败
- `Not found`: 推文不存在或无法访问

## 更多信息

详细文档请参考 [API 返回数据结构文档](./api-response-structure.md)
