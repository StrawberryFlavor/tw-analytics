# TW Analytics - Twitter数据提取系统

🚀 **解决Twitter API限流问题的专业数据提取工具** - 智能多数据源切换，一次请求获取完整推文线程和相关推文数据。

## ✨ 核心价值

- **🔄 告别限流** - 智能切换Twitter API和Playwright，突破300次/15分钟限制
- **📊 完整数据** - 一次请求获取主推文、线程推文、相关推文、用户信息
- **⚡ 即开即用** - 一键Docker部署，自动Cookie管理
- **🛡️ 生产就绪** - 多层容错，认证状态监控，API降级保护

## 🚀 快速开始

### 方式一：Docker一键部署（推荐）
```bash
git clone https://github.com/your-repo/tw-analytics.git
cd tw-analytics
./scripts/deploy.sh
```

### 方式二：本地开发
```bash
# 环境设置
source scripts/setup.sh

# 获取认证（可选，启用完整功能）
python login_twitter.py

# 启动服务
python run.py
```

## 📡 核心API

### 综合数据提取
**一次请求获取页面所有推文数据**

```bash
curl -X POST http://127.0.0.1:5100/api/tweet/comprehensive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://x.com/username/status/123456"}'
```

**响应数据：**
```json
{
  "success": true,
  "data": {
    "tweet": {
      "id": "123456",
      "text": "推文内容",
      "author": {"username": "user", "name": "Name", "verified": true},
      "metrics": {"views": 1500, "likes": 25, "retweets": 5},
      "quality_score": "high"
    },
    "thread": [],           // 线程推文
    "related": [            // 相关推文（回复、转发等）
      {"id": "789", "text": "回复内容", "quality_score": "medium"}
    ],
    "meta": {"source": "Playwright", "load_time": "8.5s"}
  }
}
```

### 其他API端点
```bash
GET  /api/v1/health              # 健康检查
GET  /api/v1/auth/status         # 认证状态
POST /api/v1/auth/refresh        # 刷新Cookie
GET  /api/v1/data-sources/status # 数据源状态
```

## 🐳 生产部署

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

## 🔧 认证管理

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

## 💡 常见问题

### ❌ API返回空的相关推文
**症状**: `related` 字段为空数组  
**原因**: Cookie无效，只能访问公开内容  
**解决**: 
```bash
# 检查认证状态
curl http://127.0.0.1:5100/api/v1/auth/status
# 如果status不是"healthy"，重新登录
python login_twitter.py
```

### ❌ Docker容器中Cookie数量为0
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

### ❌ 线上线下数据不一致
**症状**: 本地能提取11条相关推文，线上只有8条  
**原因**: 认证级别不同或时间/地理位置差异  
**解决**: 统一认证状态，将本地有效Cookie复制到线上

## 🔍 工作原理

1. **优先Twitter API** - 快速准确
2. **智能检测限流** - 监控失败率  
3. **自动切换数据源** - 无感知降级到Playwright
4. **认证状态管理** - 自动Cookie维护
5. **数据结构统一** - 一致的JSON响应格式

## 📋 注意事项

- **基础功能**: 仅需Bearer Token即可使用Twitter API
- **完整功能**: 需要登录Cookie才能获取所有相关推文
- **生产部署**: 建议Docker部署并配置认证信息
- **限流解决**: 多数据源架构彻底解决API限制

## 🔗 相关链接

- [配置说明](.env.example) - 环境变量配置模板
- [部署脚本](scripts/deploy.sh) - 一键部署脚本
- [登录工具](login_twitter.py) - Twitter Cookie获取

---

**MIT License** | 如有问题请提交 [Issue](https://github.com/StrawberryFlavor/tw-analytics/issues)
