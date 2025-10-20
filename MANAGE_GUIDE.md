# TW Analytics 管理脚本使用指南

## 概述

`scripts/manage.sh` 是TW Analytics的统一管理工具，集成了数据同步、数据更新、浏览器池管理等所有核心功能。

## 快速开始

```bash
# 查看所有可用命令
./scripts/manage.sh help

# 设置开发环境
./scripts/manage.sh setup

# 启动服务
./scripts/manage.sh start
```

## 数据同步功能

### 基础同步操作

```bash
# 测试同步（演练模式，不修改数据库）
./scripts/manage.sh sync-test

# 执行完整数据同步
./scripts/manage.sh sync

# 更新所有现有记录
./scripts/manage.sh update-all

# 测试更新操作
./scripts/manage.sh update-all-test
```

### 优先级同步

```bash
# 测试优先级同步（专门处理从未同步过的数据）
./scripts/manage.sh priority-sync-test

# 执行优先级同步
./scripts/manage.sh priority-sync
```

## 系统管理功能

### 环境管理

```bash
# 设置基础开发环境
./scripts/manage.sh setup

# 设置包含Twitter登录的完整环境
./scripts/manage.sh setup login

# 启动开发服务器
./scripts/manage.sh start

# Docker部署
./scripts/manage.sh deploy
```

### 浏览器池管理

```bash
# 重置所有浏览器实例（解决假死问题）
./scripts/manage.sh reset-browsers
```

## 命令详解

### sync-test
- **用途**: 演练模式测试同步
- **安全**: 不会修改数据库
- **输出**: 显示将要创建的记录数量和统计信息

### sync
- **用途**: 执行完整数据同步
- **功能**: 从campaign_task_submission同步到campaign_tweet_snapshot
- **确认**: 需要用户确认才会执行

### update-all
- **用途**: 更新所有现有快照记录
- **功能**: 刷新Twitter数据（views、metrics等）
- **适用**: 定期数据更新维护

### priority-sync
- **用途**: 优先处理未同步数据
- **功能**: 专门同步从未处理过的记录
- **优势**: 确保重要数据优先处理

### reset-browsers
- **用途**: 重置浏览器池
- **场景**: 解决浏览器实例假死或内存泄漏
- **操作**: 强制关闭所有chromium进程

## 使用场景

### 场景1: 首次数据同步

```bash
# 1. 先测试了解数据量
./scripts/manage.sh sync-test

# 2. 执行实际同步
./scripts/manage.sh sync
```

### 场景2: 定期数据更新

```bash
# 更新现有记录的最新数据
./scripts/manage.sh update-all-test  # 先测试
./scripts/manage.sh update-all       # 再执行
```

### 场景3: 处理重要未同步数据

```bash
# 优先处理从未同步的数据
./scripts/manage.sh priority-sync-test
./scripts/manage.sh priority-sync
```

### 场景4: 系统维护

```bash
# 浏览器池出现问题时
./scripts/manage.sh reset-browsers

# 重新启动服务
./scripts/manage.sh start
```

## 注意事项

### 安全提醒
1. **测试优先**: 生产操作前必须先运行test版本
2. **确认提示**: 所有写入操作都需要用户确认
3. **演练模式**: sync-test和update-all-test完全安全

### 性能建议
1. **大数据量**: 超过1000条记录建议分批处理
2. **网络环境**: 确保稳定的网络连接
3. **资源监控**: 注意内存和CPU使用情况

### 故障处理
1. **浏览器假死**: 运行`reset-browsers`命令
2. **同步中断**: 重新运行命令，系统会自动恢复
3. **错误日志**: 查看详细的执行日志进行排查

## 监控和日志

### 实时监控
- 执行过程中会显示详细进度
- 成功/失败统计实时更新
- 预计完成时间动态计算

### 日志记录
- 所有操作都有详细日志
- 错误信息包含具体原因和建议
- 支持按时间查询历史记录

## 常见问题

### Q: sync-test显示0条记录？
A: 可能所有数据已经同步完成，这是正常情况。

### Q: 同步过程中出现超时？
A: 运行`reset-browsers`重置浏览器池，然后重试。

### Q: 如何恢复中断的同步？
A: 重新运行相同命令，系统会自动跳过已处理的记录。

### Q: 如何查看详细错误信息？
A: 查看控制台输出，所有错误都有详细说明和建议。

---

**提示**: 所有命令都支持`--help`参数查看详细说明
