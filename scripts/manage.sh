#!/bin/bash

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="tw-analytics-api"

show_help() {
    echo "🛠️  TW Analytics 管理工具"
    echo "============================="
    echo ""
    echo "用法: ./scripts/manage.sh <命令> [选项]"
    echo ""
    echo "命令:"
    echo "  setup [login]    设置开发环境"
    echo "  start           启动开发服务器"
    echo "  deploy          Docker部署"
    echo ""
    echo "数据更新命令:"
    echo "  update          快速更新缺失字段"
    echo "  update-custom   自定义配置更新"
    echo "  update-records <ids>  更新指定记录"
    echo "  schedule        启动定时更新调度器"
    echo "  test-update     测试数据更新服务"
    echo ""
    echo "数据同步命令:"
    echo "  sync-test       测试同步（演练模式，不修改数据库）"
    echo "  sync            同步campaign数据（获取Twitter数据并创建完整记录）"
    echo "  update-all-test 测试全部更新（演练模式）"
    echo "  update-all      全部更新现有记录的Twitter数据"
    echo ""
    echo "示例:"
    echo "  ./scripts/manage.sh setup"
    echo "  ./scripts/manage.sh setup login"
    echo "  ./scripts/manage.sh start"
    echo "  ./scripts/manage.sh deploy"
    echo ""
    echo "  # 数据更新示例"
    echo "  ./scripts/manage.sh update"
    echo "  ./scripts/manage.sh update-records 237,269,270"
    echo "  ./scripts/manage.sh schedule"
    echo "  ./scripts/manage.sh test-update"
    echo ""
    echo "  # 数据同步示例"
    echo "  ./scripts/manage.sh sync-test     # 先测试，查看将创建多少记录"
    echo "  ./scripts/manage.sh sync          # 执行实际同步，创建完整Twitter记录"
    echo ""
    echo "  # 全部更新示例"
    echo "  ./scripts/manage.sh update-all-test  # 测试全部更新"
    echo "  ./scripts/manage.sh update-all       # 执行全部更新"
    echo ""
    echo "  # 优先级同步示例（专门处理未同步过的数据）"
    echo "  ./scripts/manage.sh priority-sync-test  # 测试优先级同步"
    echo "  ./scripts/manage.sh priority-sync       # 执行优先级同步"
}

setup_environment() {
    local login_mode=$1
    
    echo "🐍 设置Python环境..."
    echo "📍 项目目录: $PROJECT_ROOT"
    
    cd "$PROJECT_ROOT"
    
    # 检查Python和venv模块
    echo "🔍 检查Python环境..."
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python3未安装"
        echo "   请运行: sudo apt install python3"
        return 1
    fi
    
    local python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo "   Python版本: $python_version"
    
    # 检查venv模块是否可用
    if ! python3 -m venv --help &> /dev/null; then
        echo "❌ Python venv模块未安装"
        echo "   请运行: sudo apt install python3-venv"
        echo "   或: sudo apt install python3.$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)-venv"
        return 1
    fi
    
    VENV_PATH="$PROJECT_ROOT/.venv"
    
    # 检查虚拟环境是否完整
    if [ -d "$VENV_PATH" ] && [ ! -f "$VENV_PATH/bin/activate" ]; then
        echo "⚠️  虚拟环境不完整，重新创建..."
        rm -rf "$VENV_PATH"
    fi
    
    if [ ! -f "$VENV_PATH/bin/activate" ]; then
        echo "📦 创建虚拟环境..."
        if ! python3 -m venv "$VENV_PATH"; then
            echo "❌ 创建虚拟环境失败"
            echo "   可能的解决方案："
            echo "   1. 确保有足够的磁盘空间"
            echo "   2. 检查目录权限"
            echo "   3. 尝试手动创建: python3 -m venv .venv"
            return 1
        fi
    fi
    
    echo "⚡ 激活虚拟环境..."
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    else
        echo "❌ 无法激活虚拟环境"
        return 1
    fi
    
    echo "📈 升级pip..."
    pip install --upgrade pip > /dev/null 2>&1
    
    echo "📋 安装基础依赖..."
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements.txt" > /dev/null 2>&1
    else
        echo "⚠️  requirements.txt文件不存在"
    fi
    
    echo "✅ 基础环境设置完成!"
    
    if [ "$login_mode" = "login" ]; then
        echo ""
        echo "🎭 设置Playwright登录环境..."
        
        echo "📦 安装Playwright依赖..."
        pip install playwright beautifulsoup4 lxml > /dev/null 2>&1
        
        echo "🌐 安装Chromium浏览器..."
        playwright install chromium > /dev/null 2>&1
        
        echo "✅ 登录环境设置完成!"
    fi
    
    echo ""
    echo "⚠️  重要提示：脚本已完成环境设置，但虚拟环境还未在您的终端中激活"
    echo "📌 请在终端中运行以下命令激活虚拟环境："
    echo "    source .venv/bin/activate"
    echo ""
    echo "💡 激活后您会看到终端提示符前出现 (.venv)"
    echo "   然后可以运行："
    echo "    python run.py          # 启动服务"
    echo "    python login_twitter.py # 登录Twitter"
}

start_service() {
    echo "🚀 TW Analytics 启动脚本"
    echo "=================================="
    
    cd "$PROJECT_ROOT"
    
    # 检查虚拟环境是否存在且完整
    if [ ! -f ".venv/bin/activate" ]; then
        echo "🔧 虚拟环境不存在或不完整，先运行设置..."
        setup_environment
        if [ $? -ne 0 ]; then
            echo "❌ 环境设置失败，无法启动服务"
            return 1
        fi
        echo ""
        echo "⚠️  环境设置完成，请手动激活虚拟环境后再次运行："
        echo "    source .venv/bin/activate"
        echo "    ./scripts/manage.sh start"
        return
    fi
    
    # 检查虚拟环境是否已激活
    if [[ "$VIRTUAL_ENV" == "" ]]; then
        echo "⚠️  虚拟环境未激活"
        echo "📌 请先手动激活虚拟环境："
        echo "    source .venv/bin/activate"
        echo ""
        echo "💡 然后再次运行："
        echo "    ./scripts/manage.sh start"
        echo "    或直接运行: python run.py"
        return
    fi
    
    echo "✅ 虚拟环境已激活: $VIRTUAL_ENV"
    
    # 检查必要文件
    if [ ! -f "run.py" ]; then
        echo "❌ run.py文件不存在"
        return 1
    fi
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            echo "📝 创建环境变量文件..."
            cp .env.example .env
            echo "⚠️  请编辑 .env 文件并设置您的配置"
        else
            echo "⚠️  .env文件不存在，某些功能可能无法正常工作"
        fi
    fi
    
    echo ""
    echo "🚀 启动服务..."
    echo "=================================="
    
    # 读取.env文件中的FLASK_ENV配置
    if [ -f ".env" ]; then
        ENV_FROM_FILE=$(grep "^FLASK_ENV=" .env | cut -d'=' -f2)
        if [ "$ENV_FROM_FILE" = "production" ]; then
            echo "✅ 生产环境"
            python wsgi.py
        else
            echo "📌 开发环境"
            python run.py
        fi
    else
        # 如果没有.env文件，使用环境变量
        if [ "$FLASK_ENV" = "production" ]; then
            echo "✅ 生产环境"
            python wsgi.py
        else
            echo "📌 开发环境"
            python run.py
        fi
    fi
}

deploy_docker() {
    echo "🚀 开始部署 TW Analytics..."
    
    cd "$PROJECT_ROOT"
    
    # 检查Docker环境
    echo "🔍 检查Docker环境..."
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker未安装"
        echo "   请先安装Docker: https://docs.docker.com/engine/install/"
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        echo "❌ Docker服务未运行"
        echo "   请启动Docker服务: sudo systemctl start docker"
        return 1
    fi
    
    # 检查docker compose命令（新版本）或docker-compose（旧版本）
    local compose_cmd=""
    if docker compose version &> /dev/null; then
        compose_cmd="docker compose"
        echo "   使用: docker compose (新版本)"
    elif command -v docker-compose &> /dev/null; then
        compose_cmd="docker-compose"
        echo "   使用: docker-compose (旧版本)"
    else
        echo "❌ Docker Compose未安装"
        echo "   请安装Docker Compose:"
        echo "   - 新版本: sudo apt install docker-compose-plugin"
        echo "   - 旧版本: sudo apt install docker-compose"
        return 1
    fi
    
    echo "✅ Docker环境检查通过"
    
    mkdir -p instance
    
    # 检查必要文件
    if [ ! -f .env ]; then
        echo "⚠️  .env文件不存在，请创建并配置必要的环境变量"
        if [ -f .env.example ]; then
            echo "   参考文件: .env.example"
            echo "   运行: cp .env.example .env"
        fi
        return 1
    fi
    
    if [ ! -f docker/docker-compose.yml ]; then
        echo "❌ docker/docker-compose.yml文件不存在"
        return 1
    fi
    
    local port=${PORT:-5100}
    
    echo "🧹 全面清理环境..."
    
    # 检查端口占用
    if lsof -i :$port >/dev/null 2>&1; then
        echo "⚠️  端口 $port 被占用，尝试清理..."
        
        # 尝试停止本地Python进程
        local python_pid=$(lsof -ti :$port | grep -v "^$")
        if [ -n "$python_pid" ]; then
            echo "   停止占用端口的进程 (PID: $python_pid)..."
            kill -9 $python_pid 2>/dev/null || true
            sleep 2
        fi
    fi
    
    # 清理Docker容器
    echo "📦 清理Docker容器..."
    
    # 只清理tw-analytics相关的容器，不影响其他项目
    echo "   停止tw-analytics相关容器..."
    docker stop tw-analytics-api 2>/dev/null || true
    docker stop tw-analytics 2>/dev/null || true
    
    echo "   删除tw-analytics相关容器..."
    docker rm tw-analytics-api 2>/dev/null || true
    docker rm tw-analytics 2>/dev/null || true
    
    # 使用docker-compose down但不使用--remove-orphans以避免影响其他项目
    echo "   清理docker-compose服务..."
    $compose_cmd -f docker/docker-compose.yml --env-file .env down || true
    
    # 再次检查端口
    if lsof -i :$port >/dev/null 2>&1; then
        echo "❌ 端口 $port 仍被占用，请手动检查并停止相关进程"
        echo "   运行: lsof -i :$port"
        echo "   或: sudo netstat -tulpn | grep :$port"
        exit 1
    fi
    
    echo "✅ 环境清理完成"
    echo ""
    
    # 检查环境变量
    if ! grep -q "TWITTER_BEARER_TOKEN=" .env || grep -q "TWITTER_BEARER_TOKEN=$" .env; then
        echo "⚠️  警告: TWITTER_BEARER_TOKEN 未设置"
    fi
    
    echo "🔨 构建新镜像..."
    $compose_cmd -f docker/docker-compose.yml --env-file .env build --no-cache
    
    echo "🌟 启动服务..."
    $compose_cmd -f docker/docker-compose.yml --env-file .env up -d
    
    echo "⏳ 等待服务启动..."
    sleep 10
    
    echo "📊 容器状态："
    # 只显示tw-analytics相关的容器状态
    docker ps --filter "name=tw-analytics" --format "table {{.Names}}\t{{.Image}}\t{{.Command}}\t{{.Status}}\t{{.Ports}}"
    
    if docker ps --filter "name=tw-analytics-api" --format "{{.Status}}" | grep -q "Up"; then
        echo "✅ 服务启动成功！"
        test_service_health
    else
        echo "❌ 服务启动失败"
        echo "💡 查看日志: $compose_cmd -f docker/docker-compose.yml --env-file .env logs"
        exit 1
    fi
}

test_service_health() {
    local port=${PORT:-5100}
    
    echo "🔍 测试服务健康状态..."
    for i in {1..6}; do
        if curl -f -s "http://localhost:$port/api/v1/health" > /dev/null 2>&1; then
            echo "✅ 健康检查通过！服务运行正常"
            echo "🎉 API服务可通过 http://localhost:$port 访问"
            break
        else
            if [ $i -eq 6 ]; then
                echo "⚠️  健康检查失败，请检查服务状态"
            else
                echo "⏳ 等待服务启动... (尝试 $i/6)"
                sleep 10
            fi
        fi
    done
}

# 数据更新相关函数

check_update_environment() {
    echo "🔍 检查数据更新环境..."
    
    cd "$PROJECT_ROOT"
    
    # 检查虚拟环境
    if [ ! -f ".venv/bin/activate" ]; then
        echo "❌ 虚拟环境不存在，请先运行: ./scripts/manage.sh setup"
        return 1
    fi
    
    # 检查更新脚本
    local required_files=("quick_update.py" "advanced_update.py" "scheduled_update.py" "test_data_updater.py")
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            echo "❌ 缺少更新脚本: $file"
            return 1
        fi
    done
    
    echo "✅ 数据更新环境检查通过"
    return 0
}

run_quick_update() {
    echo "🚀 开始快速更新缺失字段..."
    echo "================================"
    
    if ! check_update_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    # 激活虚拟环境并运行更新
    source .venv/bin/activate
    python quick_update.py
    
    echo "✅ 快速更新完成"
}

run_custom_update() {
    echo "⚙️  开始自定义配置更新..."
    echo "================================"
    
    if ! check_update_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "请选择更新模式:"
    echo "1. 自定义配置"
    echo "2. 更新指定记录"
    echo "3. 带进度监控更新"
    
    read -p "输入选项 (1-3): " choice
    
    local mode_arg=""
    case $choice in
        1) mode_arg="custom" ;;
        2) mode_arg="specific" ;;
        3) mode_arg="monitor" ;;
        *) 
            echo "❌ 无效选择"
            return 1
            ;;
    esac
    
    source .venv/bin/activate
    python advanced_update.py "$mode_arg"
    
    echo "✅ 自定义更新完成"
}

run_update_records() {
    local record_ids="$1"
    
    if [ -z "$record_ids" ]; then
        echo "❌ 请提供记录ID，例如: ./scripts/manage.sh update-records 237,269,270"
        return 1
    fi
    
    echo "🎯 更新指定记录: $record_ids"
    echo "================================"
    
    if ! check_update_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    # 创建临时脚本来处理指定记录更新
    cat > temp_update_records.py << EOF
#!/usr/bin/env python3
import asyncio
import sys
from src.app.services.data_updater import create_data_updater

async def main():
    record_ids = [int(x.strip()) for x in "$record_ids".split(",")]
    print(f"🎯 更新记录ID: {record_ids}")
    
    updater = await create_data_updater()
    result = await updater.update_specific_records(record_ids)
    
    print(f"✅ 更新完成: {result.successful_updates}/{len(record_ids)} 成功")
    print(f"   成功率: {result.success_rate:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
EOF
    
    source .venv/bin/activate
    python temp_update_records.py
    rm -f temp_update_records.py
    
    echo "✅ 指定记录更新完成"
}

run_scheduler() {
    echo "⏰ 启动数据更新调度器..."
    echo "================================"
    
    if ! check_update_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    source .venv/bin/activate
    python scheduled_update.py
    
    echo "✅ 调度器已退出"
}

run_test_update() {
    echo "🧪 测试数据更新服务..."
    echo "================================"
    
    if ! check_update_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    source .venv/bin/activate
    python test_data_updater.py
    
    echo "✅ 测试完成"
}

# 数据同步相关函数

check_sync_environment() {
    echo "🔍 检查数据同步环境..."
    
    cd "$PROJECT_ROOT"
    
    # 检查虚拟环境
    if [ ! -f ".venv/bin/activate" ]; then
        echo "❌ 虚拟环境不存在，请先运行: ./scripts/manage.sh setup"
        return 1
    fi
    
    # 检查同步脚本
    if [ ! -f "sync_campaign_data.py" ]; then
        echo "❌ 缺少同步脚本: sync_campaign_data.py"
        return 1
    fi
    
    # 检查同步服务模块
    if [ ! -f "src/app/services/data_sync/sync_service.py" ]; then
        echo "❌ 缺少同步服务模块"
        return 1
    fi
    
    echo "✅ 数据同步环境检查通过"
    return 0
}

run_sync_test() {
    echo "🧪 测试数据同步（演练模式）..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "🔍 分析数据同步需求，不会修改数据库..."
    echo ""
    
    source .venv/bin/activate
    python sync_campaign_data.py --dry-run
    
    echo "✅ 同步测试完成"
}

run_sync() {
    echo "🔄 执行数据同步..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "📋 此操作将:"
    echo "   1. 从campaign_task_submission获取推文ID"
    echo "   2. 通过Twitter API获取每个推文的完整数据"  
    echo "   3. 创建包含完整信息的campaign_tweet_snapshot记录"
    echo ""
    echo "🔍 正在分析需要同步的记录数量..."
    
    # 获取需要同步的记录数量
    source .venv/bin/activate
    sync_count=$(python -c "
import asyncio
import sys
sys.path.append('.')
from src.app.services.data_sync import CampaignDataSyncService
from src.app.core.config_factory import SyncConfig
from src.app.services.database import get_database_service

async def get_sync_count():
    try:
        db_service = await get_database_service()
        config = SyncConfig.create_safe_config()
        sync_service = CampaignDataSyncService(database_service=db_service, config=config)
        sync_records = await sync_service._analyze_sync_needs()
        await db_service.close()
        return len(sync_records)
    except Exception as e:
        return 0

result = asyncio.run(get_sync_count())
print(result)
" 2>/dev/null)
    
    if [ "$sync_count" = "0" ] || [ -z "$sync_count" ]; then
        echo "❌ 无法获取同步信息，请检查数据库连接"
        return 1
    fi
    
    echo "   📊 预计创建 $sync_count 条完整记录"
    echo ""
    echo "⚠️  警告: 这将修改生产数据库!"
    echo ""
    read -p "确认要执行数据同步吗？(输入 'yes' 继续): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "❌ 操作已取消"
        return 1
    fi
    
    echo ""
    echo "🚀 开始执行数据同步..."
    
    source .venv/bin/activate
    python sync_campaign_data.py
    
    echo "✅ 数据同步执行完成"
}

run_update_all_test() {
    echo "🧪 测试全部更新（演练模式）..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "🔍 分析全部更新需求，不会修改数据库..."
    echo ""
    
    source .venv/bin/activate
    python sync_campaign_data.py --update-all --dry-run
    
    echo "✅ 全部更新测试完成"
}

run_update_all() {
    echo "🔄 执行全部更新..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "📋 此操作将:"
    echo "   1. 获取campaign_tweet_snapshot中所有现有记录"
    echo "   2. 通过Twitter API获取每个推文的最新数据"  
    echo "   3. 更新views、replies、retweets等统计数据"
    echo ""
    echo "🔍 正在分析需要更新的记录数量..."
    
    # 获取需要更新的记录数量（全部更新模式）
    source .venv/bin/activate
    update_count=$(python -c "
import asyncio
import sys
sys.path.append('.')
from src.app.services.data_sync import CampaignDataSyncService
from src.app.core.config_factory import SyncConfig
from src.app.services.database import get_database_service

async def get_update_count():
    try:
        db_service = await get_database_service()
        config = SyncConfig.create_update_all_config()
        sync_service = CampaignDataSyncService(database_service=db_service, config=config)
        sync_records = await sync_service._analyze_sync_needs()
        await db_service.close()
        return len(sync_records)
    except Exception as e:
        return 0

result = asyncio.run(get_update_count())
print(result)
" 2>/dev/null)
    
    if [ "$update_count" = "0" ] || [ -z "$update_count" ]; then
        echo "❌ 无法获取更新信息，请检查数据库连接"
        return 1
    fi
    
    echo "   📊 预计更新 $update_count 条现有记录"
    echo ""
    echo "⚠️  警告: 这将修改生产数据库中的所有推文记录!"
    echo "⚠️  此操作可能需要较长时间完成!"
    echo ""
    read -p "确认要执行全部更新吗？(输入 'yes' 继续): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "❌ 操作已取消"
        return 1
    fi
    
    echo ""
    echo "🚀 开始执行全部更新..."
    
    source .venv/bin/activate
    python sync_campaign_data.py --update-all
    
    echo "✅ 全部更新执行完成"
}

run_priority_sync_test() {
    echo "⚡ 测试优先级同步（演练模式）..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "🔍 分析优先级同步需求（专门处理从未同步过的数据），不会修改数据库..."
    echo ""
    
    source .venv/bin/activate
    python sync_campaign_data.py --priority-new --dry-run
    
    echo "✅ 优先级同步测试完成"
}

run_priority_sync() {
    echo "⚡ 执行优先级同步..."
    echo "================================"
    
    if ! check_sync_environment; then
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    
    echo "📋 优先级同步模式将:"
    echo "   1. 查找在campaign_task_submission中但不在campaign_tweet_snapshot中的记录"
    echo "   2. 这些是从未同步过的推文，优先处理"
    echo "   3. 通过Twitter API获取完整数据并创建快照记录"
    echo ""
    echo "🔍 正在分析需要优先同步的记录数量..."
    
    # 获取需要优先同步的记录数量
    source .venv/bin/activate
    priority_count=$(python -c "
import asyncio
import sys
sys.path.append('.')
from src.app.services.data_sync import CampaignDataSyncService
from src.app.core.config_factory import SyncConfig
from src.app.services.database import get_database_service

async def get_priority_count():
    try:
        db_service = await get_database_service()
        config = SyncConfig.create_priority_config()
        sync_service = CampaignDataSyncService(database_service=db_service, config=config)
        sync_records = await sync_service._analyze_sync_needs()
        await db_service.close()
        print(len(sync_records))
    except Exception as e:
        print(f'错误: {e}', file=sys.stderr)
        print('0')

result = asyncio.run(get_priority_count())
")

    if [ "$priority_count" = "0" ]; then
        echo "✅ 没有需要优先同步的记录"
        return 0
    fi
    
    echo "   ⚡ 预计创建 $priority_count 条优先记录"
    echo ""
    echo "⚠️  警告: 这将修改生产数据库!"
    echo "⚠️  此操作专门处理从未同步过的数据，通常是最重要的数据!"
    echo ""
    read -p "确认要执行优先级同步吗？(输入 'yes' 继续): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "❌ 操作已取消"
        return 1
    fi
    
    echo ""
    echo "🚀 开始执行优先级同步..."
    
    source .venv/bin/activate
    python sync_campaign_data.py --priority-new
    
    echo "✅ 优先级同步执行完成"
}



main() {
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    case "$1" in
        setup)
            setup_environment "$2"
            ;;
        start)
            start_service
            ;;
        deploy)
            deploy_docker
            ;;
        update)
            run_quick_update
            ;;
        update-custom)
            run_custom_update
            ;;
        update-records)
            run_update_records "$2"
            ;;
        schedule)
            run_scheduler
            ;;
        test-update)
            run_test_update
            ;;
        sync)
            run_sync
            ;;
        sync-test)
            run_sync_test
            ;;
        update-all-test)
            run_update_all_test
            ;;
        update-all)
            run_update_all
            ;;
        priority-sync)
            run_priority_sync
            ;;
        priority-sync-test)
            run_priority_sync_test
            ;;
        reset-browsers)
            reset_browsers
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "❌ 未知命令: $1"
            echo "运行 './scripts/manage.sh help' 查看帮助"
            exit 1
            ;;
    esac
}

reset_browsers() {
    echo "🔄 重置所有浏览器实例..."
    echo "================================"
    
    cd "$PROJECT_ROOT"
    
    # 检查虚拟环境
    if [ ! -f ".venv/bin/activate" ]; then
        echo "❌ 虚拟环境不存在，请先运行: ./scripts/manage.sh setup"
        return 1
    fi
    
    source .venv/bin/activate
    
    echo "⚠️  此操作将强制关闭并重建所有浏览器实例"
    echo "   用于解决浏览器实例假死或内存泄漏问题"
    echo ""
    
    # 杀死所有chromium进程
    echo "🧹 清理残留的chromium进程..."
    pkill -f chromium || true
    pkill -f chrome || true
    
    echo "✅ 浏览器实例重置完成"
    echo "   下次同步时将自动创建新的浏览器实例"
}

main "$@"