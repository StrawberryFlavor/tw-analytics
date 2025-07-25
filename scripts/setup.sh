#!/bin/bash
# 统一的环境设置脚本
# 使用方法: source scripts/setup.sh [login]

# 检查是否使用了source命令
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    echo "❌ 错误: 请使用 source 命令执行此脚本!"
    echo "✅ 正确用法: source scripts/setup.sh"
    echo "❌ 错误用法: ./scripts/setup.sh"
    exit 1
fi

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"

echo "🐍 设置Python环境..."
echo "📍 项目目录: $PROJECT_ROOT"

# 检查是否已有虚拟环境
if [ ! -d "$VENV_PATH" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv "$VENV_PATH"
fi

# 激活虚拟环境
echo "⚡ 激活虚拟环境..."
source "$VENV_PATH/bin/activate"

# 升级pip
echo "📈 升级pip..."
pip install --upgrade pip > /dev/null 2>&1

# 安装基础依赖
echo "📋 安装基础依赖..."
pip install -r "$PROJECT_ROOT/requirements.txt" > /dev/null 2>&1

echo "✅ 基础环境设置完成!"
echo "💡 当前Python: $(which python)"

# 检查是否需要设置登录环境
if [ "$1" = "login" ]; then
    echo ""
    echo "🎭 设置Playwright登录环境..."
    
    # 安装额外依赖
    echo "📦 安装Playwright依赖..."
    pip install playwright beautifulsoup4 lxml > /dev/null 2>&1
    
    echo "🌐 安装Chromium浏览器..."
    playwright install chromium > /dev/null 2>&1
    
    echo "✅ 登录环境设置完成!"
    echo ""
    echo "📝 提示："
    echo "  • 运行登录脚本: python login_twitter.py"
    echo "  • 如在国内，建议先设置代理:"
    echo "    export https_proxy=http://127.0.0.1:7890"
    echo "    export http_proxy=http://127.0.0.1:7890"
    echo ""
else
    echo ""
    echo "📝 提示："
    echo "  • 启动服务: python run.py"
    echo "  • 设置登录环境: source scripts/setup.sh login"
fi