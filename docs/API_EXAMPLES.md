# Twitter浏览量提升API使用指南

## 启动服务

```bash
# 1. 进入项目目录
cd /home/ubuntu/tw-analytics

# 2. 设置环境变量
export FLASK_APP=src/app
export FLASK_ENV=development

# 3. 启动服务
python -m flask run --host=0.0.0.0 --port=5000
```

## API端点总览

| 方法 | 端点 | 描述 | 特点 |
|------|------|------|------|
| GET | `/api/v1/view-booster/health` | 健康检查 | - |
| GET | `/api/v1/view-booster/config` | 获取配置信息 | - |
| GET | `/api/v1/view-booster/accounts/status` | 账户状态 | - |
| **POST** | **`/api/v1/view-booster/boost`** | **浏览器模式提升** | 真实浏览器 |
| **POST** | **`/api/v1/view-booster/fast-start`** | **速刷模式提升** | 10-100x 速度 |
| GET | `/api/v1/view-booster/tasks` | 查询所有任务 | 任务列表 |
| GET | `/api/v1/view-booster/tasks/{task_id}` | 查询任务状态 | 实时进度 |
| POST | `/api/v1/view-booster/tasks/{task_id}/stop` | 停止任务 | 立即停止 |

## 使用示例

### 1. 健康检查
```bash
curl http://localhost:5100/api/v1/view-booster/health
```

### 2. 启动浏览量提升任务（两种模式）

#### 速刷模式（Fast Mode）- 速度优先
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://x.com/binineex9/status/1952271082482020729"
    ],
    "target_views": 1000,
    "max_concurrent_requests": 10,
    "use_proxy_pool": true,
    "request_interval": [1, 3],
    "retry_on_failure": true,
    "max_retries": 3
  }'
```

**速刷模式特点**：
- 速度: 10-100x 快于浏览器模式
- 资源: 极低内存和CPU占用
- 并发: 支持 10-50+ 并发请求
- 适用: 大批量快速提升
- 注意: 无浏览器渲染，纯HTTP请求

#### 浏览器模式（Browser Mode）- 稳定可靠
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/boost \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://x.com/binineex9/status/1952645582184452472"
    ],
    "target_views": 2000,
    "max_instances": 7,
    "max_tabs_per_instance": 1,
    "refresh_interval": 8,
    "headless": true,
    "use_proxy_pool": false
  }'
```

#### 单一代理模式
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/boost \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/1234567890"],
    "target_views": 1000,
    "max_instances": 5,
    "max_tabs_per_instance": 2,
    "refresh_interval": 10,
    "headless": true,
    "use_proxy_pool": false,
    "proxy": "http://proxy.example.com:8080"
  }'
```

#### 有头模式（开发调试）
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/boost \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/Cryptoxiangu/status/1951418971858649285?t=V3sA84-neePuPrA5_ReYJg&s=19"],
    "target_views": 50,
    "max_instances": 2,
    "max_tabs_per_instance": 1,
    "refresh_interval": 12,
    "headless": false,
    "use_proxy_pool": true
  }'
```

### 3. 查询所有任务
```bash
curl http://localhost:5100/api/v1/view-booster/tasks
```

响应：
```json
{
  "success": true,
  "data": {
    "total": 2,
    "tasks": [
      {
        "task_id": "task-id-1",
        "type": "view_boost",
        "status": "running",
        "created_at": "2025-08-03T13:30:00",
        "progress": {
          "successful_views": 25,
          "target_views": 100
        }
      }
    ]
  }
}
```

### 4. 查询任务进度
```bash
curl http://localhost:5100/api/v1/view-booster/tasks/{task_id}
```

### 5. 停止任务
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/tasks/{task_id}/stop
```

响应：
```json
{
  "success": true,
  "message": "任务 {task_id} 已停止"
}
```

## 模式对比与选择

### 模式对比表

| 特性 | 速刷模式 (fast-start) | 浏览器模式 (boost) |
|------|---------------------|--------------------|
| **速度** | 极快 (10-100x) | 正常 |
| **资源占用** | 极低 | 较高 |
| **并发数** | 10-50+ | 3-10 |
| **稳定性** | 中等 | 高 |
| **真实性** | 中等 | 高 |
| **适用场景** | 大批量快速 | 精准稳定 |

### 速刷模式参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | Array | - | Twitter/X URL列表 |
| `target_views` | Integer | 1000 | 目标浏览量 |
| `max_concurrent_requests` | Integer | 10 | 最大并发请求数 |
| `request_interval` | Array | [1, 3] | 请求间隔范围（秒） |
| `use_proxy_pool` | Boolean | true | **使用代理池 (优先级高于环境变量)** |
| `proxy` | String | null | **单一代理URL (最高优先级)** |
| `retry_on_failure` | Boolean | true | 失败重试 |
| `max_retries` | Integer | 3 | 最大重试次数 |

### 代理配置优先级示例

#### 示例1：禁用代理池（API参数优先）
```bash
# 环境变量设置了启用代理池
export PROXY_POOL_ENABLED=true

# 但API请求可以覆盖这个设置
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/123"],
    "use_proxy_pool": false,  # ← 这个参数优先级最高
    "target_views": 100
  }'
```

#### 示例2：使用单一代理（最高优先级）
```bash
# 指定单一代理，优先级最高
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/123"],
    "proxy": "http://your.proxy.com:8080",  # ← 最高优先级
    "use_proxy_pool": true,  # ← 被忽略
    "target_views": 100
  }'
```

#### 示例3：使用环境变量默认值
```bash
# 环境变量设置
export PROXY_POOL_ENABLED=true

# API请求不指定任何代理参数，使用环境变量默认值
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/123"],
    # 没有 proxy 和 use_proxy_pool 参数，使用环境变量 true
    "target_views": 100
  }'
```

## 浏览器模式设置

### 环境变量配置
```bash
# 设置默认无头模式
export VB_HEADLESS=true

# 设置浏览器模式
export VB_BROWSER_MODE=headless

# 设置代理
export VB_PROXY=http://proxy.example.com:8080

# 设置最大实例数
export VB_MAX_INSTANCES=5
```

### 请求参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | Array | - | Twitter/X URL列表 |
| `headless` | Boolean | `true` | 无头模式开关 |
| `max_instances` | Integer | 3 | 最大浏览器实例数（1-10） |
| `max_tabs_per_instance` | Integer | 3 | 每实例最大标签页数（1-5） |
| `refresh_interval` | Integer | 10 | 刷新间隔秒数（最小5） |
| `use_proxy_pool` | Boolean | `false` | **启用代理池（推荐）** |
| `proxy` | String | null | 单一代理地址（use_proxy_pool=false时使用） |

### 模式选择建议

#### 代理池模式 (use_proxy_pool: true) - 强烈推荐
- **适用场景**: 生产环境、高并发访问
- **优点**: 每个实例使用不同代理，避免IP检测
- **缺点**: 需要配置 `scripts/proxies.txt` 文件
- **配置**: 自动读取 `scripts/proxies.txt` 中的代理列表

**代理池配置**：
```bash
# 在 scripts/proxies.txt 文件中配置代理列表（一行一个）
http://username:password@proxy-server.com:8080
http://192.168.1.100:3128
https://secure-proxy.com:443
socks5://username:password@socks-server.com:1080
```

#### 无头模式 (headless: true)
- **适用场景**: 生产环境、服务器部署
- **优点**: 资源占用少、运行稳定
- **缺点**: 无法观察浏览器行为

#### 有头模式 (headless: false)
- **适用场景**: 开发调试、问题排查
- **优点**: 可视化调试、观察访问过程
- **缺点**: 资源占用大、需要图形界面

## 返回数据示例

### 成功响应
```json
{
  "success": true,
  "message": "多URL浏览量提升完成: 25 次成功访问",
  "data": {
    "urls": ["https://x.com/user/status/123"],
    "url_count": 1,
    "instances_used": 5,
    "total_tabs": 5,
    "total_views": 25,
    "successful_views": 25,
    "failed_views": 0,
    "success_rate": 100.0,
    "config": {
      "max_instances": 5,
      "max_tabs_per_instance": 1,
      "refresh_interval": 8,
      "headless": true,
      "use_proxy_pool": true,
      "proxy": "proxy_pool"
    }
  }
}
```

### 错误响应
```json
{
  "success": false,
  "error": "No active accounts available"
}
```

## 9. 快速刷浏览量（HTTP版本）

### 端点
```
POST /api/v1/view-booster/fast-start
```

### 请求示例

#### 基本使用
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/elonmusk/status/1234567890"],
    "target_views": 100
  }'
```

#### 批量快速刷量
```bash
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://x.com/user1/status/111111111",
      "https://x.com/user2/status/222222222"
    ],
    "target_views": 200,
    "max_concurrent_requests": 20,
    "use_proxy_pool": true
  }'
```

### 成功响应
```json
{
  "success": true,
  "message": "Fast view boost task started",
  "data": {
    "task_id": "task_1234567890",
    "status": "running",
    "urls": ["https://x.com/elonmusk/status/1234567890"],
    "target_views": 100,
    "config": {
      "max_concurrent_requests": 10,
      "use_proxy_pool": true,
      "request_interval": [1, 3]
    }
  }
}
```

### 性能对比

| 特性 | 浏览器版本 (/start) | 快速版本 (/fast-start) |
|------|---------------------|------------------------|
| 速度 | 慢 | 快（10倍以上） |
| 资源 | 高 | 低 |
| 并发 | 3-5个实例 | 10-50个请求 |
| 适用 | 精确模拟 | 大批量刷量 |

## 故障排除

### 1. 服务启动失败
```bash
# 检查端口是否被占用
lsof -i :5000

# 更换端口
python -m flask run --host=0.0.0.0 --port=5001
```

### 2. 账户相关错误
```bash
# 检查账户文件
ls -la scripts/accounts.json

# 验证账户状态
curl http://localhost:5100/api/v1/view-booster/accounts/status
```

### 3. 浏览器启动失败
```bash
# 安装Playwright浏览器
playwright install chromium

# 检查依赖
pip install playwright flask
```

## Postman 测试

### 导入到Postman
1. 创建新的Collection: "Twitter View Booster"
2. 添加以下请求:

#### GET Health Check
- URL: `http://localhost:5100/api/v1/view-booster/health`
- Method: GET

#### POST Multi-URL Boost (代理池模式)
- URL: `http://localhost:5100/api/v1/view-booster/boost`
- Method: POST
- Headers: `Content-Type: application/json`
- Body (raw JSON):
```json
{
  "urls": ["https://x.com/username/status/1234567890"],
  "max_instances": 5,
  "max_tabs_per_instance": 1,
  "refresh_interval": 8,
  "headless": true,
  "use_proxy_pool": true
}
```

## 性能调优建议

### 大量URL处理（代理池模式）
```json
{
  "urls": ["url1", "url2", "url3", "url4", "url5"],
  "max_instances": 10,
  "max_tabs_per_instance": 3,
  "refresh_interval": 6,
  "headless": true,
  "use_proxy_pool": true
}
```

### 稳定性优先（代理池 + 保守配置）
```json
{
  "urls": ["url1", "url2"],
  "max_instances": 3,
  "max_tabs_per_instance": 2,
  "refresh_interval": 12,
  "headless": true,
  "use_proxy_pool": true
}
```

### 速度优先（代理池 + 激进配置）
```json
{
  "urls": ["url1"],
  "max_instances": 8,
  "max_tabs_per_instance": 1,
  "refresh_interval": 5,
  "headless": true,
  "use_proxy_pool": true
}
```

## 安全提醒

1. **代理池安全**:
   - 使用可信赖的代理服务商
   - 定期更新 `scripts/proxies.txt` 文件
   - 避免使用免费公共代理

2. **不要在生产环境使用有头模式**
3. **定期更新账户token**
4. **使用HTTPS代理保护隐私**
5. **遵守Twitter服务条款**
