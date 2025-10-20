# 快速刷量 API 使用指南

## 概述

快速刷量功能提供了一个高效的HTTP版本，无需启动浏览器即可增加Twitter推文浏览量。相比浏览器版本，它具有更快的速度和更低的资源消耗。

## API 端点

### 启动快速刷量

**端点**: `POST /api/v1/view-booster/fast-start`

**描述**: 启动快速刷量任务，使用HTTP请求直接访问推文页面

### 请求参数

```json
{
  "urls": ["https://x.com/username/status/123456789"],  // 目标推文URL列表
  "target_views": 100,                                   // 目标浏览量（可选，默认100）
  "max_concurrent_requests": 10,                         // 最大并发请求数（可选，默认10）
  "request_interval": [1, 3],                           // 请求间隔范围（秒）（可选）
  "use_proxy_pool": true,                               // 是否使用代理池（可选，默认true）
  "proxy": "http://proxy.example.com:8080"              // 单一代理URL（可选，最高优先级）
}
```

### 响应格式

**成功响应** (200 OK):
```json
{
  "success": true,
  "message": "Fast view boost task started",
  "data": {
    "task_id": "task_123456789",
    "status": "running",
    "urls": ["https://x.com/username/status/123456789"],
    "target_views": 100,
    "config": {
      "max_concurrent_requests": 10,
      "use_proxy_pool": true
    }
  }
}
```

**错误响应** (400/500):
```json
{
  "success": false,
  "error": "错误信息"
}
```

## 使用示例

### 1. 基本使用

```bash
# 刷单个推文
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/binineex9/status/1952645582184452472"],
    "target_views": 2000
  }'
```

### 2. 批量刷量

```bash
# 同时刷多个推文
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://x.com/user1/status/111111111",
      "https://x.com/user2/status/222222222",
      "https://x.com/user3/status/333333333"
    ],
    "target_views": 200,
    "max_concurrent_requests": 15
  }'
```

### 3. 自定义配置

#### 使用自定义代理
```bash
# 使用指定的单一代理
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/123456789"],
    "target_views": 100,
    "proxy": "http://your.proxy.com:8080"
  }'
```

#### 禁用代理池
```bash
# 禁用代理池，使用环境变量的本地代理或直连
curl -X POST http://localhost:5100/api/v1/view-booster/fast-start \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://x.com/username/status/123456789"],
    "target_views": 100,
    "max_concurrent_requests": 5,
    "request_interval": [2, 5],
    "use_proxy_pool": false
  }'
```

## Python 客户端示例

```python
import requests

# API 端点
url = "http://localhost:5100/api/v1/view-booster/fast-start"

# 请求数据
data = {
    "urls": ["https://x.com/elonmusk/status/1234567890"],
    "target_views": 100,
    "max_concurrent_requests": 10,
    "use_proxy_pool": True
}

# 发送请求
response = requests.post(url, json=data)

# 处理响应
if response.status_code == 200:
    result = response.json()
    if result["success"]:
        print(f"✅ 任务启动成功！")
        print(f"任务ID: {result['data']['task_id']}")
        print(f"状态: {result['data']['status']}")
    else:
        print(f"❌ 任务启动失败: {result['error']}")
else:
    print(f"❌ 请求失败: {response.status_code}")
```

## 查询任务状态

启动任务后，可以使用任务ID查询状态：

```bash
# 查询任务状态
curl http://localhost:5100/api/v1/view-booster/tasks/{task_id}

# 停止任务
curl -X POST http://localhost:5100/api/v1/view-booster/tasks/{task_id}/stop
```

## 性能对比

| 特性 | 浏览器版本 | 快速版本 |
|------|------------|----------|
| **速度** | 慢（需要加载页面） | 快（直接HTTP请求） |
| **资源消耗** | 高（浏览器进程） | 低（仅HTTP连接） |
| **并发能力** | 受限于浏览器数量 | 可大量并发 |
| **稳定性** | 高 | 高 |
| **适用场景** | 精确模拟用户行为 | 大批量快速刷量 |

## 环境变量配置

快速刷量功能支持通过环境变量配置智能代理管理：

```bash
# 智能代理管理器配置
NETWORK_MODE=auto                # 网络模式: auto(自动), direct(直连), local_proxy(本地代理), proxy_pool(代理池)
LOCAL_PROXY=127.0.0.1:7890      # 本地代理地址(科学上网用)
PROXY_POOL_ENABLED=true         # 是否启用代理池(业务需求)
```

### 网络模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `auto` | 自动检测网络环境，智能选择代理策略 | **推荐使用** |
| `direct` | 强制直连，不使用任何代理 | 服务器环境，网络无限制 |
| `local_proxy` | 强制使用本地代理 | 本地开发，需要科学上网 |
| `proxy_pool` | 强制使用代理池 | 业务需求，需要隐藏真实IP |

### 智能选择逻辑

- **能直连x.com** + **代理池启用** → 使用代理池(业务需求)
- **不能直连x.com** + **本地代理配置** → 使用本地代理(科学上网)
- **能直连x.com** + **代理池禁用** → 直连
- **不能直连x.com** + **无本地代理** → 抛出网络错误

### 参数优先级规则

系统采用 **API参数优先** 的设计原则：

| 优先级 | 配置层级 | 作用范围 | 示例 |
|--------|----------|----------|------|
| **1 (最高)** | 单一代理参数 | 单次请求 | `"proxy": "http://proxy.com:8080"` |
| **2 (高)** | 代理池参数 | 单次请求 | `"use_proxy_pool": false` |
| **3 (中等)** | 环境变量 | 全局默认 | `PROXY_POOL_ENABLED=true` |

**工作原理**：
1. **proxy 参数存在** → 使用指定代理，忽略其他所有设置
2. **use_proxy_pool 参数存在** → 使用代理池设置，忽略环境变量
3. **只有环境变量** → 使用环境变量默认值

**示例场景**：
```bash
# 环境变量设置
PROXY_POOL_ENABLED=true

# 请求1 - 单一代理优先级最高
{
  "proxy": "http://custom.proxy.com:8080",  ← 最高优先级，直接使用
  "use_proxy_pool": true  // 被忽略
}

# 请求2 - use_proxy_pool 覆盖环境变量
{
  "use_proxy_pool": false  ← 覆盖环境变量，禁用代理池
}

# 请求3 - 使用环境变量默认值  
{
  // 没有 proxy 和 use_proxy_pool 参数，使用环境变量 true
}
```

## 注意事项

1. **账户管理**: 系统会自动轮换使用配置的账户
2. **代理设置**: 建议使用代理池以避免IP限制
3. **请求频率**: 请合理设置请求间隔，避免触发限制
4. **错误处理**: 系统会自动重试失败的请求
5. **环境变量**: 推荐使用 `NETWORK_MODE=auto` 让系统自动选择最佳代理策略

## 常见问题

### Q: 快速版本和浏览器版本有什么区别？
A: 快速版本使用HTTP请求直接访问推文页面，速度更快但不执行JavaScript。浏览器版本完整模拟用户行为，更接近真实访问。

### Q: 可以同时运行多个任务吗？
A: 可以，系统支持多任务并发运行。

### Q: 如何选择使用哪个版本？
A: 
- 需要快速大量刷量：使用快速版本 (`/fast-start`)
- 需要精确模拟用户行为：使用浏览器版本 (`/start`)

### Q: 代理连接失败怎么办？
A: 系统会自动降级到不使用代理，或者您可以设置 `use_proxy_pool: false` 禁用代理。