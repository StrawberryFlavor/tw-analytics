# Apify Twitter 数据源集成指南

## 概述

本系统现已集成 Apify 作为第三方 Twitter 数据源，提供更强大的推文数据爬取能力。Apify 数据源在现有的多数据源架构中作为备用选择，优先级为：**Playwright > Apify > TwitterAPI**

## 快速配置

### 1. 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# Apify 集成配置
APIFY_ENABLE=true
APIFY_API_TOKEN=your_apify_api_token_here
APIFY_ACTOR_ID=apidojo/tweet-scraper
APIFY_TIMEOUT=120
```

### 2. 获取 Apify API 令牌

1. 访问 [Apify Console](https://console.apify.com/account/integrations)
2. 登录或注册账户
3. 在 "Integrations" 页面生成 API 令牌
4. 将令牌复制到 `APIFY_API_TOKEN` 环境变量

## API 端点

### 单个推文数据获取

**端点**: `POST /tweet/comprehensive-apify`

**请求示例**:
```bash
curl -X POST http://localhost:5100/tweet/comprehensive-apify \
  -H "Content-Type: application/json" \
  -d '{"url": "https://twitter.com/user/status/1234567890"}'
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "primary_tweet": {
      "tweet_id": "1234567890",
      "text": "推文内容",
      "author": {
        "username": "user",
        "name": "用户名",
        "followers_count": 1000
      },
      "metrics": {
        "views": 5000,
        "likes": 100,
        "retweets": 50,
        "replies": 25
      },
      "timestamp": "2024-01-01T12:00:00Z"
    }
  },
  "meta": {
    "source": "apify",
    "timestamp": 1704096000,
    "total_tweets": 1
  }
}
```

### 批量推文数据获取

**端点**: `POST /tweets/batch-apify`

**请求限制**: 最多 10 个 URL

**请求示例**:
```bash
curl -X POST http://localhost:5100/tweets/batch-apify \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://twitter.com/user/status/1234567890",
      "https://twitter.com/user/status/1234567891"
    ]
  }'
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "url": "https://twitter.com/user/status/1234567890",
        "data": { /* 推文数据 */ },
        "meta": {
          "source": "apify",
          "timestamp": 1704096000
        }
      }
    ],
    "errors": [],
    "summary": {
      "total_requested": 2,
      "successful": 2,
      "failed": 0
    }
  }
}
```

## 数据格式说明

### 推文数据结构

```json
{
  "primary_tweet": {
    "tweet_id": "string",
    "text": "string",
    "author": {
      "id": "string",
      "username": "string",
      "name": "string",
      "description": "string",
      "followers_count": 0,
      "following_count": 0,
      "verified": false
    },
    "timestamp": "ISO 8601 时间戳",
    "metrics": {
      "views": 0,
      "likes": 0,
      "retweets": 0,
      "replies": 0,
      "quotes": 0
    },
    "media": [
      {
        "type": "photo|video",
        "url": "string",
        "alt_text": "string"
      }
    ],
    "hashtags": ["string"],
    "mentions": ["string"],
    "links": ["string"],
    "tweet_type": "normal|reply|retweet|quote",
    "language": "string"
  },
  "thread_tweets": [],  // 线程推文
  "related_tweets": [], // 相关推文
  "extraction_metadata": {
    "timestamp": 1704096000,
    "source": "apify",
    "total_tweets_found": 1
  }
}
```

## 错误处理

### 常见错误码

- **400**: 参数错误，检查 URL 格式
- **401**: API 令牌无效
- **404**: 推文不存在或已删除
- **503**: Apify 服务不可用，检查配置
- **500**: 系统内部错误

### 错误响应示例

```json
{
  "success": false,
  "error": "Service unavailable",
  "message": "Apify data source is not configured"
}
```

## 性能考虑

### 超时设置

- 默认超时：120 秒
- 可通过 `APIFY_TIMEOUT` 环境变量调整
- 建议范围：60-300 秒

### 并发限制

- 单个请求：无特殊限制
- 批量请求：最多 10 个 URL
- Apify Actor 并发受账户套餐限制

### 成本优化

- Apify 按运行时间计费
- 建议优先使用 Playwright 数据源
- 仅在其他数据源不可用时使用 Apify

## 故障排除

### 配置检查

检查数据源状态：
```bash
curl http://localhost:5100/data-sources/status
```

### 常见问题

1. **"Apify data source is not configured"**
   - 检查 `APIFY_ENABLE=true`
   - 确认 `APIFY_API_TOKEN` 已设置

2. **"Actor run timed out"**
   - 增加 `APIFY_TIMEOUT` 值
   - 检查网络连接

3. **"No data found"**
   - 验证推文 URL 格式
   - 确认推文存在且可访问

## 监控和日志

### 日志级别

系统会记录以下信息：
- Actor 运行开始/完成
- 数据提取结果
- 错误和异常

### 监控指标

建议监控：
- Apify Actor 运行时间
- 成功/失败率
- API 调用频率
- 数据提取质量

## 最佳实践

1. **数据源优先级**: 优先使用 Playwright，Apify 作为备用
2. **错误处理**: 实现适当的重试机制
3. **成本控制**: 监控 Apify 使用量
4. **数据质量**: 验证提取的数据完整性
5. **缓存策略**: 考虑对结果进行缓存以减少重复请求