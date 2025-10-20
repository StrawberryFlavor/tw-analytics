# 智能截图系统配置说明

## 截图存储位置

截图文件存储在：
```
/tmp/twitter_screenshots/YYYYMMDD/
```

- **基础目录**：`/tmp/twitter_screenshots/`
- **日期子目录**：按日期创建子目录，如 `20250803/`
- **自动清理**：过期目录会自动删除

## 环境配置详情

### Production (生产环境)
```
screenshot_env: "production"
```
- **截图频率**：每 **100次访问** 截图一次
- **存储限制**：最大 **50MB**
- **保留时间**：**12小时** 后自动清理
- 调试模式：关闭
- 截图类型：
  - 首次成功访问
  - 每100次里程碑
  - 错误发生时
  - 任务完成时

### Staging (预发布环境)
```
screenshot_env: "staging"
```
- **截图频率**：每 **50次访问** 截图一次
- **存储限制**：最大 **100MB**
- **保留时间**：**24小时** 后自动清理
- 调试模式：关闭
- **截图类型**：同生产环境

### Development (开发环境)
```
screenshot_env: "development"
```
- **截图频率**：每 **5次访问** 截图一次
- **存储限制**：最大 **200MB**
- **保留时间**：**48小时** 后自动清理
- 调试模式：开启
- 最大调试截图：每个标签页最多 50 张
- 截图类型：
  - 首次成功访问
  - 每5次调试截图
  - 每20次里程碑
  - 错误发生时
  - 任务完成时

### Disabled (禁用截图)
```
screenshot_env: "disabled"
```
- **截图功能**：完全禁用，不生成任何截图

## 截图数量预估

### 生产环境预估
假设目标浏览量100次，3个实例，每实例2个标签页：

| 截图类型 | 触发条件 | 数量 |
|---------|---------|------|
| 首次访问 | 每个标签页第1次成功 | 6张 |
| 里程碑 | 每100次访问 | 6张 |
| 任务完成 | 达到目标后 | 6张 |
| **总计** | | **约18张** |

### 开发环境预估
相同条件下：

| 截图类型 | 触发条件 | 数量 |
|---------|---------|------|
| 首次访问 | 每个标签页第1次成功 | 6张 |
| 调试截图 | 每5次访问 | 约120张 |
| 里程碑 | 每20次访问 | 约30张 |
| 任务完成 | 达到目标后 | 6张 |
| **总计** | | **约162张** |

## 文件命名规则

截图文件名格式：
```
{tab_id}_v{view_count}_{type}_{timestamp}.png
```

示例：
```
0-0_v1_first_load_143052.png    # 标签页0-0，第1次访问，首次加载，14:30:52
1-2_v50_milestone_143855.png    # 标签页1-2，第50次访问，里程碑，14:38:55
2-1_v23_error_144201.png        # 标签页2-1，第23次访问，错误，14:42:01
```

## 自动清理机制

### 按时间清理
- **过期判断**：基于目录创建时间
- **清理频率**：每次启动时检查
- **清理单位**：整个日期目录

### 按存储限制清理
- **触发条件**：总存储超过配置限制
- **清理策略**：删除最旧的20%文件
- **检查频率**：每次截图前检查

## 截图触发逻辑

### 首次访问截图
```
tab_info['views_count'] == 1 && config.first_screenshot == true
```

### 里程碑截图
```
view_count % config.milestone_interval == 0
```

### 调试模式截图
```
debug_mode == true && 
view_count % debug_interval == 0 && 
tab_screenshots < debug_max_screenshots
```

### 错误截图
```
发生异常时 && config.error_screenshot == true
```

### 任务完成截图
```
成功访问数 >= 目标访问数 && config.final_screenshot == true
```

## 监控和统计

运行结束时会显示截图统计：
```
截图统计:
   截图环境: production
   生成截图: 18
   存储占用: 12.5MB
   文件总数: 18
```

## 注意事项

1. **生产环境建议**：使用 `production` 配置，平衡功能和性能
2. **调试时**：使用 `development` 配置，获得详细的截图记录
3. **磁盘空间**：系统会自动管理，但建议定期监控 `/tmp` 空间
4. **性能影响**：截图操作会增加2-3秒的访问时间
5. **权限问题**：确保程序对 `/tmp` 目录有读写权限

## 修改配置

在创建 `ViewBoosterConfig` 时指定：
```python
config = ViewBoosterConfig(
    screenshot_env="production",  # 或 staging, development, disabled
    # ... 其他配置
)
```

自定义截图配置：
```python
from screenshot_manager import ScreenshotConfig, ScreenshotManager

custom_config = ScreenshotConfig(
    enabled=True,
    milestone_interval=200,  # 每200次截图
    max_storage_mb=30,       # 限制30MB
    retention_hours=6        # 6小时后清理
)
```
