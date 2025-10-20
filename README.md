# TW Analytics - Twitter数据提取与分析系统

**企业级Twitter工具集** - 数据提取、浏览量提升、数据同步三大核心功能，智能多数据源切换，一次请求获取完整推文数据。

## 核心价值

### 数据提取系统
- 告别限流 - 智能切换Twitter API和Playwright，突破300次/15分钟限制
- 完整数据 - 一次请求获取主推文、线程推文、相关推文、用户信息
- 生产就绪 - 多层容错，认证状态监控，API降级保护
- 高性能架构 - 浏览器池并发管理，智能负载均衡，自动故障恢复

### 浏览量提升系统
- 高成功率 - 多重触发机制，确保真实浏览量增长
- 高效率 - 100个账户93秒完成，支持代理轮换
- 智能重试 - 自动错误处理和连接恢复
- 实时监控 - 成功率统计和性能指标

### 数据同步系统
- 全链路同步 - campaign_task_submission → campaign_tweet_snapshot 完整数据流
- 智能容错 - 风控检测、错误重试、资源清理一体化
- 高效处理 - 批量同步、优先级队列、进度追踪
- 灵活管理 - 支持全量更新、增量同步、优先级同步

### 通用特性
- 即开即用 - 一键Docker部署，自动Cookie管理
- 实时监控 - 系统健康状态监控，性能指标追踪，问题预警机制

## 快速开始

### 数据提取系统

#### 方式一：Docker一键部署（推荐）
```bash
git clone https://github.com/your-repo/tw-analytics.git
cd tw-analytics
./scripts/deploy.sh
```

#### 方式二：本地开发
```bash
# 环境设置
source scripts/setup.sh

# 获取认证（可选，启用完整功能）
python login_twitter.py

# 启动服务
python run.py
```

### 数据同步系统

#### 同步数据到快照表
```bash
# 测试同步（演练模式）
./scripts/manage.sh sync-test

# 执行完整同步
./scripts/manage.sh sync

# 优先级同步（未同步数据）
./scripts/manage.sh priority-sync

# 更新现有记录
./scripts/manage.sh update-all
```

### 浏览量提升系统

#### 快速使用
```bash
cd scripts
python view_booster_multi.py
```

#### 配置要求
- **账户文件**: `accounts.json` - 包含100个有效的auth_token
- **代理文件**: `proxies.txt` - 包含代理服务器列表（可选）
- **运行参数**: 并发数、延迟时间、运行轮次可自定义

## 核心API

> 详细文档:
> - [API返回数据结构详解](./docs/api-response-structure.md) - 完整的数据结构说明和解析指南
> - [API快速参考](./docs/quick-reference.md) - 常用字段和代码片段速查

### 综合数据提取
**一次请求获取页面所有推文数据，统一结构设计**

```bash
# 统一的API调用 - user_tweet + primary_tweet双字段结构
curl -X POST http://127.0.0.1:5100/api/tweet/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/username/status/123456"}'
```

**响应数据结构：**

**原创推文：**
```json
{
  "success": true,
  "data": {
    "user_tweet": {
      "id": "123456",
      "text": "原创推文内容",
      "author": {
        "username": "user", 
        "name": "用户名",
        "verified": true
      },
      "time": "2024-01-15T10:30:00Z",
      "type": "original",
      "metrics": {
        "likes": 25,
        "retweets": 5, 
        "replies": 3,
        "views": 1500
      }
    },
    "primary_tweet": null  // 原创推文没有主推文
  }
}
```

**引用推文：**
```json
{
  "user_tweet": {
    "type": "quote",
    "text": "我的引用评论",
    "action_info": {
      "target": {
        "author": "original_user",
        "text": "被引用的原文",
        "url": "https://x.com/original_user/status/789",
        "id": "789"
      }
    }
  },
  "primary_tweet": {
    "type": "original",
    "text": "被引用的原文",
    "metrics": {"likes": 100, "retweets": 50}  // 真实数据
  }
}
```

### 其他API端点

**基础功能**
```bash
GET  /api/v1/health                    # 健康检查
GET  /api/v1/tweet/{id}/views          # 获取推文浏览量
GET  /api/v1/tweet/{id}                # 获取推文信息
GET  /api/v1/tweet/{id}/engagement     # 获取推文互动率
POST /api/v1/tweets/views              # 批量获取浏览量
```

**用户功能**
```bash
GET  /api/v1/user/{username}           # 获取用户信息
GET  /api/v1/user/{username}/tweets    # 获取用户推文
GET  /api/v1/search?q=keyword          # 搜索推文
```

**管理功能**
```bash
GET  /api/v1/auth/status               # 认证状态
POST /api/v1/auth/refresh              # 刷新Cookie
GET  /api/v1/data-sources/status       # 数据源状态
POST /api/v1/data-sources/reset        # 重置数据源
```

**浏览器池监控**
```bash
GET  /api/v1/pool/status               # 浏览器池状态
GET  /api/v1/pool/instances            # 浏览器实例详情
POST /api/v1/pool/warmup               # 预热浏览器池
POST /api/v1/pool/cleanup              # 清理无效实例
GET  /api/v1/pool/metrics              # 性能指标统计
```

**数据同步接口**
```bash
# 通过主同步脚本调用
python sync_campaign_data.py --dry-run      # 演练模式
python sync_campaign_data.py               # 执行同步
python sync_campaign_data.py --update-all  # 更新全部
python sync_campaign_data.py --priority-new # 优先级同步
```

**批量功能**
```bash
POST /api/v1/tweet/by-url              # 通过URL获取推文
POST /api/v1/tweets/by-urls            # 批量通过URL获取推文
```

**使用示例**
```bash
# 获取推文浏览量
curl http://127.0.0.1:5100/api/v1/tweet/123456/views

# 获取用户信息
curl http://127.0.0.1:5100/api/v1/user/elonmusk

# 搜索推文
curl "http://127.0.0.1:5100/api/v1/search?q=AI&count=10"

# 批量获取浏览量
curl -X POST http://127.0.0.1:5100/api/v1/tweets/views \
  -H "Content-Type: application/json" \
  -d '{"tweet_ids": ["123456", "789012"]}'

# 监控浏览器池状态
curl http://127.0.0.1:5100/api/v1/pool/status

# 查看性能指标
curl http://127.0.0.1:5100/api/v1/pool/metrics
```

## 生产部署

### Docker部署
```bash
# 一键部署
./scripts/deploy.sh

# 手动部署
docker-compose -f docker/docker-compose.yml up -d

# 查看状态
docker-compose -f docker/docker-compose.yml logs -f
```

### 环境配置
```bash
# 必需配置
TWITTER_BEARER_TOKEN=your_token

# 可选配置（启用完整功能）
TWITTER_USERNAME=your_username  
TWITTER_PASSWORD=your_password
```

## 认证管理

### 检查Cookie状态
```bash
curl http://127.0.0.1:5100/api/v1/auth/status

# 健康状态响应
{
  "data": {
    "authentication": {
      "cookie_count": 7,
      "status": "healthy"    // 或 "empty_cookies", "no_cookies"
    }
  }
}
```

### Cookie问题修复
```bash
# 重新获取Cookie
python login_twitter.py

# 手动刷新
curl -X POST http://127.0.0.1:5100/api/v1/auth/refresh
```

## 常见问题

### API返回空的相关推文
**症状**: `related` 字段为空数组  
**原因**: Cookie无效，只能访问公开内容  
**解决**: 
```bash
# 检查认证状态
curl http://127.0.0.1:5100/api/v1/auth/status
# 如果status不是"healthy"，重新登录
python login_twitter.py
```

### Docker容器中Cookie数量为0
**症状**: `"cookie_count": 0`  
**原因**: Volume挂载问题或Cookie文件损坏  
**解决**:
```bash
# 检查volume挂载
docker exec tw-analytics-api ls -la /app/instance/
# 重新获取Cookie
python login_twitter.py
# 重启容器
docker-compose -f docker/docker-compose.yml restart
```

### 线上线下数据不一致
**症状**: 本地能提取11条相关推文，线上只有8条  
**原因**: 认证级别不同或时间/地理位置差异  
**解决**: 统一认证状态，将本地有效Cookie复制到线上

## 工作原理

### 核心架构
1. **优先Twitter API** - 快速准确的官方接口
2. **智能检测限流** - 实时监控失败率和响应时间  
3. **自动切换数据源** - 无感知降级到Playwright浏览器池
4. **认证状态管理** - 自动Cookie维护和刷新
5. **数据结构统一** - 一致的JSON响应格式

### 浏览器池管理
- **并发控制** - 最大5个并发浏览器实例，避免资源竞争
- **健康检查** - 每60秒自动检测浏览器状态，及时清理失效实例
- **智能恢复** - 检测到故障时自动重启，支持熔断保护
- **负载均衡** - 智能分配请求到可用的浏览器实例
- **资源优化** - 自动回收空闲实例，预热机制提升响应速度

### 依赖注入系统
- **单例管理** - 确保服务实例唯一性，避免重复创建
- **模块化设计** - 每个组件职责单一，易于维护和测试
- **容器化管理** - 统一的依赖管理，支持开发和生产环境切换

## 浏览量提升系统详解

### 技术原理
浏览量提升系统基于深度分析Twitter的浏览量统计机制，采用多重触发策略确保真实有效的浏览量增长：

1. **页面访问触发** - 模拟真实用户访问推文页面
2. **多重统计事件** - 同时触发4种不同的统计事件：
   - `impression` - 标准展示事件
   - `tweet_impression` - 推文展示事件  
   - `view` - 视图统计事件
   - `dwell_time` - 页面停留统计

### 核心特性

#### 高成功率保障
- **100%成功率** - 经过优化的多重触发机制
- **智能重试** - 自动检测失败并重试
- **错误处理** - 完善的异常捕获和处理

#### 高效能执行
- **并发处理** - 支持10个并发线程同时执行
- **批次管理** - 智能分批处理，避免资源竞争
- **时间控制** - 可配置延迟时间，模拟真实用户行为

#### 代理管理
- **自动轮换** - 支持11个代理自动轮换使用
- **故障转移** - 代理失败时自动切换
- **负载均衡** - 智能分配请求到不同代理

### 使用示例

#### 基础使用
```bash
cd scripts
python twitter_booster.py
# 按提示输入推文URL和参数
```

#### 批量处理
```python
from twitter_booster import TwitterBoosterEnhanced

booster = TwitterBoosterEnhanced()
urls = [
    "https://x.com/user1/status/123456",
    "https://x.com/user2/status/789012"
]
booster.start(urls, workers=10, delay=1.2, rounds=2)
```

#### 性能配置
- **workers**: 并发线程数 (推荐: 8-12)
- **delay**: 账户间延迟秒数 (推荐: 1.0-2.0)
- **rounds**: 执行轮次 (推荐: 1-3)

### 统计示例
```
统计:
   时长: 93.2秒
   账户: 100
   成功: 100
   成功率: 100.0%
   方法: 页面访问 + 多重事件统计
   代理: 启用 (11个)
```

### 项目结构
```
tw-analytics/
├── src/app/services/
│   ├── data_sync/             # 数据同步服务
│   ├── data_updater/          # 数据更新服务
│   ├── database/              # 数据库服务抽象
│   ├── data_sources/          # 数据源管理
│   └── browser_pool/          # 浏览器池管理
├── scripts/
│   ├── manage.sh              # 统一管理脚本
│   ├── view_booster_multi.py  # 浏览量提升工具
│   ├── accounts.json          # 账户配置
│   └── proxies.txt           # 代理配置
├── sync_campaign_data.py      # 主数据同步脚本
└── README.md                  # 项目文档
```

## 注意事项

### 数据提取系统
- **基础功能**: 仅需Bearer Token即可使用Twitter API
- **完整功能**: 需要登录Cookie才能获取所有相关推文
- **生产部署**: 建议Docker部署并配置认证信息
- **限流解决**: 多数据源架构彻底解决API限制
- **性能优化**: 浏览器池预热后首次请求响应时间可提升至3-5秒
- **资源管理**: 建议生产环境至少分配2GB内存用于浏览器池运行
- **监控告警**: 可通过`/api/v1/pool/metrics`接口集成到监控系统

### 数据同步系统
- **数据库连接**: 自动连接到生产MySQL数据库
- **同步策略**: 支持全量同步、增量同步、优先级同步
- **错误处理**: 智能风控检测、自动重试、资源清理
- **性能优化**: 批处理、并发控制、浏览器池管理
- **进度追踪**: 实时进度显示、详细日志记录
- **安全保障**: 演练模式、数据验证、回滚机制

### 浏览量提升系统
- **账户要求**: 需要100个有效的Twitter auth_token
- **代理配置**: 支持HTTP和SOCKS5代理，建议使用10+个代理
- **运行环境**: Python 3.7+，需要requests库
- **安全考虑**: 遵循KISS原则，代码简洁易审查
- **效果保证**: 采用真实浏览行为模拟，确保浏览量有效增长
- **频率控制**: 建议单个推文不超过每小时3轮，避免异常检测

## 相关链接

- [配置说明](.env.example) - 环境变量配置模板
- [管理脚本](scripts/manage.sh) - 统一管理工具，支持所有功能
- [数据同步脚本](sync_campaign_data.py) - 主数据同步工具
- [登录工具](login_twitter.py) - 智能Twitter Cookie获取，支持邮箱验证
- [开发指南](CLAUDE.md) - 项目开发规范和代码风格指南

## 🆕 最新功能

### v2.0 更新内容
- 全新数据同步系统 - 完整的campaign数据同步到快照表
- 智能浏览器池 - 自动故障恢复、负载均衡、资源清理
- 风控检测优化 - 智能区分真实风控和权限限制
- 统一管理脚本 - scripts/manage.sh集成所有功能
- 性能优化 - 实例使用限制从100降到30，避免假死
- 完善错误处理 - 多层级资源清理、超时保护机制

---

**MIT License** | 如有问题请提交 [Issue](https://github.com/StrawberryFlavor/tw-analytics/issues)
