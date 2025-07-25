#!/bin/bash

# Docker一键部署脚本

set -e

echo "🐳 TW Analytics - Docker一键部署"
echo "========================================="

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 未找到Docker，请先安装Docker"
    echo "   安装指南: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ 错误: 未找到Docker Compose，请先安装Docker Compose"
    echo "   安装指南: https://docs.docker.com/compose/install/"
    exit 1
fi

# 检查环境变量文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📝 创建环境变量文件..."
        cp .env.example .env
        echo "⚠️  请编辑 .env 文件并设置您的 TWITTER_BEARER_TOKEN"
        echo ""
        read -p "是否现在编辑 .env 文件？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        echo "❌ 错误: 未找到 .env.example 文件"
        exit 1
    fi
fi

# 加载环境变量
if [ -f ".env" ]; then
    # 只导出有效的环境变量，忽略注释和空行，处理行内注释
    set -a  # 自动导出变量
    source <(cat .env | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | sed 's/#.*$//' | sed 's/[[:space:]]*$//')
    set +a  # 关闭自动导出
fi

# 检查TWITTER_BEARER_TOKEN
if [ -z "$TWITTER_BEARER_TOKEN" ] || [ "$TWITTER_BEARER_TOKEN" = "your_bearer_token_here" ]; then
    echo "❌ 错误: TWITTER_BEARER_TOKEN 未配置"
    echo "   请编辑 .env 文件并设置正确的 Bearer Token"
    exit 1
fi

echo "✅ 配置检查通过"
echo ""

# 显示部署信息
PORT=${PORT:-5000}
echo "📋 部署信息:"
echo "   - 服务端口: $PORT"
echo "   - 环境: ${FLASK_ENV:-production}"
echo "   - 健康检查: http://localhost:$PORT/api/v1/health"
echo ""

# 询问是否继续
read -p "是否开始部署？(Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "部署已取消"
    exit 0
fi

echo "🔄 停止现有容器..."
docker-compose -f docker/docker-compose.yml down --remove-orphans || true

echo "🌐 确保Docker网络存在..."
docker network create docker-network 2>/dev/null || echo "网络已存在"

echo "🏗️  构建Docker镜像..."
docker-compose -f docker/docker-compose.yml build --no-cache

echo "🚀 启动服务..."
docker-compose -f docker/docker-compose.yml up -d

echo ""
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
if docker-compose -f docker/docker-compose.yml ps | grep -q "Up"; then
    echo "✅ 服务启动成功！"
    echo ""
    echo "📡 服务地址:"
    echo "   - API服务: http://localhost:$PORT"
    echo "   - 健康检查: http://localhost:$PORT/api/v1/health"
    echo "   - API文档: 查看 README.md"
    echo ""
    echo "🔧 管理命令:"
    echo "   - 查看日志: docker-compose -f docker/docker-compose.yml logs -f"
    echo "   - 停止服务: docker-compose -f docker/docker-compose.yml down"
    echo "   - 重启服务: docker-compose -f docker/docker-compose.yml restart"
    echo ""
    
    # 测试健康检查
    echo "🔍 测试服务健康状态..."
    # 使用Docker内部健康检查，因为端口没有暴露到主机
    for i in {1..3}; do
        health_status=$(docker inspect --format='{{.State.Health.Status}}' tw-analytics-api 2>/dev/null || echo "unknown")
        if [ "$health_status" = "healthy" ]; then
            echo "✅ 健康检查通过！服务运行正常"
            echo "   注意：服务仅在Docker网络内部可访问"
            break
        else
            if [ $i -eq 3 ]; then
                echo "⚠️  服务健康状态: $health_status"
                echo "   使用以下命令检查服务状态："
                echo "   docker logs tw-analytics-api"
                echo "   docker exec tw-analytics-api curl http://localhost:5100/api/v1/health"
            else
                echo "⏳ 等待服务健康检查... (尝试 $i/3，当前状态: $health_status)"
                sleep 5
            fi
        fi
    done
else
    echo "❌ 服务启动失败，请查看日志:"
    docker-compose -f docker/docker-compose.yml logs
    exit 1
fi