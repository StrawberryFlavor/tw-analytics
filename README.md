# TW Analytics - Twitter数据分析系统

基于Flask的Twitter数据分析API，**支持多数据源智能切换**，彻底解决Twitter API限流问题。专业的推特数据提取与分析工具。

## 🚀 核心特性

- **🔄 多数据源架构** - Twitter API限流时自动切换到Playwright爬虫
- **⚡ 智能切换** - 无缝切换，用户无感知
- **🆕 综合数据提取** - 一次请求获取页面所有可见数据，告别多次请求
- **🔍 完整功能** - 推文浏览量、用户信息、批量查询、线程提取
- **🎭 简洁设计** - 一次登录，长期使用
- **🛡️ 高可用** - 解决官方API 300次/15分钟限制
- **🌐 RESTful API** - 标准HTTP接口
- **📦 Python客户端** - 开箱即用

## 📁 项目结构

```
tw-analytics/
├── 📦 核心应用
│   ├── src/app/              # Flask Web应用
│   │   ├── api/              # API路由
│   │   ├── models/           # 数据模型
│   │   ├── services/         # 业务服务层（多数据源）
│   │   └── config.py         # 配置管理
│   └── src/client/           # Python客户端
│       └── twitter_client.py
├── 🛠️ 脚本工具
│   ├── scripts/setup.sh         # 统一环境设置脚本
│   ├── scripts/start.sh         # 一键启动服务
│   └── scripts/deploy.sh         # Docker部署
├── 🎭 多数据源工具
│   └── login_twitter.py      # 一次性Twitter登录
├── 🐳 容器部署
│   ├── docker/Dockerfile
│   ├── docker/docker-compose.yml
│   └── docker/gunicorn.conf.py
├── 📋 配置文件
│   ├── .env.example         # 环境变量模板
│   ├── requirements.txt     # Python依赖
│   └── run.py              # 服务启动入口
├── 🧪 测试工具
│   ├── test_system.py      # 系统功能测试
│   └── tests/              # 单元测试（预留）
└── 📖 文档
    ├── README.md           # 使用说明
    └── CLAUDE.md           # AI规范
```

## ⚡ 快速开始

### 🎯 方式一：基础使用（仅Twitter API）

```bash
# 1. 设置环境和依赖
source scripts/setup.sh

# 2. 配置Token
cp .env.example .env
# 编辑 .env 文件，设置 TWITTER_BEARER_TOKEN

# 3. 启动服务
python run.py
```

### 🚀 方式二：完整功能（多数据源，解决限流）

```bash
# 1. 设置完整环境（包含Playwright）
source scripts/setup.sh login

# 2. 配置环境变量（可选，也可交互式输入）
cp .env.example .env
# 编辑 .env 设置：
# - TWITTER_BEARER_TOKEN
# - TWITTER_USERNAME, TWITTER_PASSWORD
# - PLAYWRIGHT_PROXY（如需代理）

# 3. 一次性登录Twitter（获取cookies）
python login_twitter.py

# 4. 启动服务（现在支持自动切换）
python run.py
```

### 🔄 方式三：一键启动（自动化）

```bash
# 直接运行启动脚本（会自动设置基础环境）
./scripts/start.sh
```

**脚本说明：**
- `setup.sh` - 统一的环境设置脚本，支持参数：
  - `source scripts/setup.sh` - 基础环境
  - `source scripts/setup.sh login` - 完整环境（含Playwright）
- `start.sh` - 一键启动服务（内部调用setup.sh）

### 🐳 Docker部署

```bash
# 先本地登录获取cookies
python login_twitter.py

# Docker部署（挂载cookies）
docker run -d -p 5100:5100 \
  -v $(pwd)/instance:/app/instance \
  --name tw-analytics-api tw-analytics-app
```

## 使用方式

### Python客户端调用

```python
from client import TwitterClient

# 从环境变量加载
client = TwitterClient.from_env()

# 获取推特浏览量
views = client.get_tweet_views("1234567890123456789")
print(f"浏览量: {views}")
```

### HTTP API调用

```bash
# 获取推特浏览量
curl http://127.0.0.1:5100/api/v1/tweet/1234567890123456789/views

# 获取用户信息
curl http://127.0.0.1:5100/api/v1/user/elonmusk
```

## Docker部署（内部网络）

### 环境要求
- Docker
- Docker Compose

### 部署说明

**⚠️ 重要**: Docker部署配置为内部网络访问，不对外暴露端口。服务运行在端口5100上，只能通过Docker网络名`docker-network`访问。

### 快速部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置 TWITTER_BEARER_TOKEN

# 2. 启动服务
docker-compose -f docker/docker-compose.yml up -d

# 3. 查看服务状态
docker-compose -f docker/docker-compose.yml ps
```

### Docker网络访问

服务启动后，其他Docker容器可以通过以下方式访问：

```bash
# 容器内访问地址
http://tw-analytics-api:5100

# 示例：在其他容器中使用API
docker run --rm \
  --network docker-network \
  curlimages/curl \
  curl http://tw-analytics-api:5100/api/v1/health
```

### 在应用中集成

参考 `docker/docker-compose.example.yml` 了解如何在其他服务中使用Twitter API：

```yaml
services:
  your-app:
    image: your-app:latest
    networks:
      - docker-network
    environment:
      - TWITTER_API_URL=http://tw-analytics-api:5100
```

### 常用命令

```bash
# 查看日志
docker-compose -f docker/docker-compose.yml logs -f

# 重启服务
docker-compose -f docker/docker-compose.yml restart

# 停止服务
docker-compose -f docker/docker-compose.yml down
```

## API文档

### Python客户端接口

#### TwitterClient类

```python
from client import TwitterClient

# 初始化
client = TwitterClient.from_env()  # 从环境变量
# 或
client = TwitterClient("your_bearer_token")  # 直接传入
```

#### 主要方法

##### `get_tweet_views(tweet_id: str) -> int`
获取推特浏览量，支持推特ID或URL。

##### `get_tweet_info(tweet_id: str) -> Dict[str, Any]`
获取推特完整信息，包含文本、作者、指标等。

##### `get_user_info(username: str) -> Dict[str, Any]`
获取用户信息，包含粉丝数、推特数等统计。

##### `get_user_recent_tweets(username: str, count: int = 5) -> List[Dict[str, Any]]`
获取用户最近推特列表。

##### `search_tweets(keyword: str, count: int = 10) -> List[Dict[str, Any]]`
搜索推特，按热度排序。

##### `get_engagement_rate(tweet_id: str) -> Dict[str, Any]`
计算推特互动率。

##### `batch_get_views(tweet_ids: List[str]) -> Dict[str, int]`
批量获取多个推特的浏览量。

### Flask API接口

启动服务后，可通过HTTP调用以下接口：

#### 基础信息
- `GET /api/v1/health` - 健康检查

#### 推特相关
- `GET /api/v1/tweet/{tweet_id}/views` - 获取推特浏览量
- `GET /api/v1/tweet/{tweet_id}` - 获取推特完整信息
- `GET /api/v1/tweet/{tweet_id}/engagement` - 获取推文互动率
- `POST /api/v1/tweets/views` - 批量获取推文浏览量
- `POST /api/tweet/comprehensive` - 🆕 **综合数据提取** - 一次获取页面所有数据

#### 🆕 综合数据提取接口详解

**功能特点：**
- ⚡ **高效提取** - 一次页面加载获取所有可见数据
- 📊 **全面数据** - 主推文、线程、回复、用户信息一应俱全
- 🛡️ **降级保护** - 多层错误处理确保服务可用性

**请求格式：**
```bash
# 完整格式（默认）
curl -X POST http://127.0.0.1:5100/api/tweet/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/elonmusk/status/1234567890123456789"}'

# 简洁格式（推荐）- 去除冗余字段，数据结构更清晰
curl -X POST http://127.0.0.1:5100/api/tweet/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/elonmusk/status/1234567890123456789"}'

```

**响应数据结构（优化格式）：**
```json
{
  "success": true,
  "data": {
    "tweet": {
      "id": "1234567890123456789",
      "text": "推文内容...",
      "author": {
        "username": "elonmusk",
        "name": "Elon Musk",
        "avatar": "https://pbs.twimg.com/profile_images/...",
        "verified": true
      },
      "time": "2025-07-23T04:24:48.000Z",
      "type": "original",
      "quality_score": "high",
      "metrics": {
        "views": 1500000,
        "likes": 25000,
        "retweets": 5000,
        "replies": 1200,
        "quotes": 800,
        "bookmarks": 3000
      },
      "media": [
        {
          "type": "image",
          "url": "https://pbs.twimg.com/media/...",
          "alt_text": "图像"
        }
      ],
      "links": [
        {
          "url": "https://example.com",
          "text": "外部链接"
        }
      ],
      "hashtags": ["#AI", "#Tesla"],
      "mentions": ["@someone"],
      "language": "en"
    },
    "thread": [],
    "related": [],
    "context": {
      "page_type": "tweet",
      "theme": "light",
      "language": "zh"
    },
    "meta": {
      "source": "Playwright",
      "load_time": "8.61s",
      "timestamp": "2025-07-24T20:29:29.326888"
    }
  },
  "message": "综合数据提取完成"
}
```

**完整格式数据结构：**
```json
{
  "success": true,
  "data": {
    "primary_tweet": {
      "tweet_id": "1234567890123456789",
      "text": "推文内容...",
      "author": {
        "username": "elonmusk",
        "display_name": "Elon Musk", 
        "avatar_url": "https://pbs.twimg.com/profile_images/...",
        "is_verified": true,
        "profile_url": "https://twitter.com/elonmusk"
      },
      "timestamp": "2025-07-23T04:24:48.000Z",
      "language": "en",
      "tweet_type": "normal",  // normal, quote, retweet, reply
      "metrics": {
        "views": 1500000,
        "likes": 25000,
        "retweets": 5000,
        "replies": 1200,
        "quotes": 800,
        "bookmarks": 3000,
        "shares": 0
      },
      "media": [
        {
          "type": "image",
          "url": "https://pbs.twimg.com/media/...",
          "alt_text": "图像",
          "format": "jpg"
        }
      ],
      "links": [
        {
          "url": "https://example.com",
          "text": "链接文本",
          "type": "external"  // external, tweet, profile, photo
        }
      ],
      "hashtags": ["#AI", "#Tesla"],
      "mentions": ["@someone"],
      "quoted_tweet": null,      // 引用推文数据（如果是引用推文）
      "reply_context": null,     // 回复上下文（如果是回复）
      "location": null           // 位置信息（如果有）
    },
    "thread_tweets": [
      // 同一作者的相关推文（线程），数据结构同primary_tweet
    ],
    "related_tweets": [
      // 页面上的其他推文（回复、引用等），数据结构同primary_tweet
    ],
    "user_profile": {},  // 用户资料信息（目前为空）
    "page_context": {
      "page_type": "tweet",      // tweet, profile, search, hashtag
      "language": "zh",
      "theme": "light",          // light, dark
      "is_logged_in": false
    },
    "extraction_metadata": {
      "timestamp": "2025-07-24T20:29:29.326888",
      "source": "Playwright",
      "page_url": "https://x.com/elonmusk/status/1234567890123456789",
      "final_url": "https://x.com/elonmusk/status/1234567890123456789",
      "target_tweet_id": "1234567890123456789",
      "page_load_time": "8.61s"
    }
  },
  "message": "综合数据提取完成"
}
```

**数据字段说明：**
- `primary_tweet`: 目标推文（主要推文）
- `thread_tweets`: 同一作者的线程推文
- `related_tweets`: 页面上的其他相关推文（回复、转发等）
- `tweet_type`: 推文类型（normal-普通, quote-引用, retweet-转发, reply-回复）
- `page_context`: 页面上下文信息（页面类型、语言、主题等）
- `extraction_metadata`: 提取过程的元数据信息

**特殊场景处理：**
- **回复推文**: 如果提供的URL是回复推文，系统会智能选择最有价值的推文作为主推文，并在 `meta.target_tweet` 中记录原始请求的推文信息
- **推文类型**: `type` 字段标识推文类型（original-原创、reply-回复、retweet-转发、quote-引用）
- **质量评分**: `quality_score` 字段评估内容质量（high-高质量、medium-中等、low-低质量）

#### 用户相关
- `GET /api/v1/user/{username}` - 获取用户信息
- `GET /api/v1/user/{username}/tweets?count=10` - 获取用户推特

#### 搜索
- `GET /api/v1/search?q=keyword&count=10` - 搜索推特

#### 数据源监控 🆕
- `GET /api/v1/data-sources/status` - 查看数据源状态
- `POST /api/v1/data-sources/reset` - 重置数据源状态

#### 认证管理 🆕
- `GET /api/v1/auth/status` - 查看Cookie认证状态
- `POST /api/v1/auth/refresh` - 强制刷新Cookies

#### 响应格式
```json
{
  "success": true,
  "data": {
    // 具体数据
  }
}
```

#### 数据源状态示例
```json
{
  "success": true,
  "data": {
    "sources": {
      "TwitterAPI": {
        "available": true,
        "healthy": true,
        "error_count": 0,
        "last_error_time": 0
      },
      "Playwright": {
        "available": true,
        "healthy": true,
        "error_count": 0,
        "last_error_time": 0
      }
    },
    "manager_initialized": true
  }
}
```

### 数据模型

#### TwitterData
推特数据模型，包含以下属性：
- `tweet_id`: 推特ID
- `text`: 推特内容
- `author_id`: 作者ID
- `author_username`: 作者用户名
- `created_at`: 创建时间
- `view_count`: 浏览量
- `like_count`: 点赞数
- `retweet_count`: 转发数
- `reply_count`: 回复数
- `quote_count`: 引用数

#### UserData
用户数据模型，包含以下属性：
- `user_id`: 用户ID
- `username`: 用户名
- `name`: 显示名
- `description`: 用户描述
- `followers_count`: 粉丝数
- `following_count`: 关注数
- `tweet_count`: 推特数
- `created_at`: 账号创建时间

## 便捷函数

快速使用，无需创建客户端实例：

```python
from client import get_tweet_views, get_user_info

# 快速获取推特浏览量（从环境变量读取token）
views = get_tweet_views("1234567890123456789")

# 快速获取用户信息
user = get_user_info("elonmusk")
```

## 错误处理

系统使用自定义的`TwitterException`来处理Twitter API相关错误：

```python
from app.models import TwitterException

try:
    tweet_info = client.get_tweet_info("invalid_id")
except TwitterException as e:
    print(f"Twitter API错误: {e}")
```

## 使用示例

```python
# Python客户端使用示例
from client import TwitterClient

# 创建客户端
client = TwitterClient.from_env()

# 获取推特浏览量
views = client.get_tweet_views("1234567890123456789")
print(f"浏览量: {views:,}")

# 获取推特详细信息
tweet_info = client.get_tweet_info("1234567890123456789")
print(f"内容: {tweet_info['text']}")
print(f"作者: @{tweet_info['author']}")

# 获取用户信息
user_info = client.get_user_info("elonmusk")
print(f"粉丝数: {user_info['stats']['followers']:,}")

# 批量获取浏览量
tweet_ids = ["1234567890123456789", "9876543210987654321"]
views_data = client.batch_get_views(tweet_ids)
for tweet_id, views in views_data.items():
    print(f"{tweet_id}: {views:,} 浏览量")
```

## 🔧 环境配置说明

### 🔑 必需配置
- `TWITTER_BEARER_TOKEN`: Twitter API Bearer Token

### 🚀 多数据源配置（可选，启用后解决限流问题）
- `TWITTER_USERNAME`: Twitter用户名/邮箱
- `TWITTER_PASSWORD`: Twitter密码  
- `TWITTER_EMAIL`: 备用邮箱（用于登录验证，可选）
- `PLAYWRIGHT_HEADLESS`: 是否无头模式（默认true，开发时可设为false）
- `PLAYWRIGHT_PROXY`: 代理地址，支持 http://, https://, socks5://

### 🍪 Cookie持久化策略 🆕
系统现在支持智能Cookie管理，**无需手动重新登录**：

**自动化特性：**
- ✅ **智能检测** - 自动检测Cookie有效性（每小时检查一次）
- ✅ **自动刷新** - Cookie过期时自动重新登录
- ✅ **健康监控** - 提供Cookie状态监控API
- ✅ **零干预** - 配置好环境变量后完全自动化

**使用方式：**
```bash
# 1. 首次设置（二选一）
# 方式A: 手动登录（适合开发环境）
python login_twitter.py

# 方式B: 环境变量配置（适合生产环境）
export TWITTER_USERNAME=your_username
export TWITTER_PASSWORD=your_password
export TWITTER_EMAIL=your_email  # 可选

# 2. 启动服务（Cookie会自动维护）
python run.py

# 3. 监控认证状态
curl http://127.0.0.1:5100/api/v1/auth/status

# 4. 手动刷新Cookie（如需要）
curl -X POST http://127.0.0.1:5100/api/v1/auth/refresh
```

**认证状态说明：**
- `healthy` - Cookie有效，工作正常
- `aging` - Cookie较旧但仍有效，建议关注
- `needs_validation` - 需要验证Cookie有效性
- `no_cookies` - 没有Cookie文件，需要首次登录

### 🎭 Playwright代理配置示例
```bash
# HTTP代理（常用）
PLAYWRIGHT_PROXY=http://127.0.0.1:7890

# SOCKS5代理
PLAYWRIGHT_PROXY=socks5://127.0.0.1:7890

# HTTPS代理
PLAYWRIGHT_PROXY=https://127.0.0.1:7890

# 不使用代理（注释掉或留空）
# PLAYWRIGHT_PROXY=
```

### 📝 其他配置（都有默认值）
- `HOST`: 服务监听地址（默认127.0.0.1）
- `PORT`: 服务端口（默认5100）
- `MAX_TWEETS_PER_REQUEST`: 单次请求最大推特数（默认100）
- `MAX_BATCH_SIZE`: 批量请求最大数量（默认50）
- `DEFAULT_TWEET_COUNT`: 默认推特数量（默认10）
- `LOG_LEVEL`: 日志级别（默认INFO）

## 🔍 系统工作原理

1. **优先使用Twitter API** - 数据准确，速度快
2. **智能检测限流** - 监控API调用失败率
3. **自动切换数据源** - 限流时切换到Playwright爬虫
4. **无感知体验** - 用户端完全透明
5. **自动恢复** - 限流解除后切回官方API

## 📋 注意事项

1. **基础功能**：仅需Bearer Token即可使用
2. **完整功能**：Cookie现支持自动管理，配置环境变量或运行`login_twitter.py`
3. **限流解决**：多数据源架构彻底解决300次/15分钟限制
4. **数据一致性**：不同数据源返回统一格式
5. **代理配置**：只有设置`PLAYWRIGHT_PROXY`才使用代理，不会自动使用系统代理
6. **调试模式**：设置`PLAYWRIGHT_HEADLESS=false`可显示浏览器窗口用于调试
7. **生产部署**：建议Docker并挂载cookies文件
8. **🆕 Cookie自动管理**：配置登录凭据后系统会自动维护Cookie，无需手动干预

## 许可证

MIT License