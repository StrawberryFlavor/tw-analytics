#!/bin/bash
# TW Analytics系统启动脚本

set -e

echo "🚀 TW Analytics 启动脚本"
echo "=================================="

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 设置虚拟环境
echo "🔧 设置虚拟环境..."
source scripts/setup.sh

# 检查环境变量文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📝 创建环境变量文件..."
        cp .env.example .env
        echo "⚠️  请编辑 .env 文件并设置您的 TWITTER_BEARER_TOKEN"
        echo "   配置模板: .env.example"
    else
        echo "⚠️  未找到 .env.example 文件"
    fi
fi

# 检查TWITTER_BEARER_TOKEN
if [ -z "$TWITTER_BEARER_TOKEN" ] && [ -f ".env" ]; then
    # 尝试从.env文件加载
    if grep -q "TWITTER_BEARER_TOKEN=" .env && ! grep -q "TWITTER_BEARER_TOKEN=your_bearer_token_here" .env; then
        echo "✅ 从 .env 文件加载配置"
    else
        echo "⚠️  警告: TWITTER_BEARER_TOKEN 未配置"
        echo "   请编辑 .env 文件或设置环境变量"
        echo ""
        read -p "是否继续启动？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "启动已取消"
            exit 1
        fi
    fi
elif [ -n "$TWITTER_BEARER_TOKEN" ]; then
    echo "✅ 检测到环境变量 TWITTER_BEARER_TOKEN"
fi

echo ""
echo "🚀 启动Flask服务..."
echo "=================================="

# 启动服务
python run.py