#!/bin/bash
# ===== 供应商邮件翻译系统 - 服务器部署脚本 =====
# 使用方法: ./deploy.sh [start|stop|restart|update]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查依赖
check_deps() {
    log_info "检查依赖..."

    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi

    if ! command -v node &> /dev/null; then
        log_error "Node.js 未安装"
        exit 1
    fi

    if ! command -v mysql &> /dev/null; then
        log_warn "MySQL 客户端未安装（可选）"
    fi
}

# 安装后端依赖
setup_backend() {
    log_info "配置后端..."
    cd "$BACKEND_DIR"

    # 创建虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建 Python 虚拟环境..."
        python3 -m venv venv
    fi

    # 激活虚拟环境并安装依赖
    source "$VENV_DIR/bin/activate"
    pip install -r requirements.txt

    # 检查 .env 文件
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在，请复制 .env.example 并配置"
        cp .env.example .env
        log_info "已创建 .env，请编辑配置后重新运行"
        exit 1
    fi

    deactivate
}

# 安装前端依赖
setup_frontend() {
    log_info "配置前端..."
    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        log_info "安装前端依赖..."
        npm install
    fi
}

# 启动服务
start_services() {
    log_info "启动服务..."

    # 启动后端
    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"

    log_info "启动后端服务 (端口 8000)..."
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
    echo $! > backend.pid

    deactivate

    # 启动前端开发服务器（生产环境可选）
    # cd "$FRONTEND_DIR"
    # nohup npm run dev > frontend.log 2>&1 &
    # echo $! > frontend.pid

    log_info "服务已启动"
    log_info "后端 API: http://localhost:8000"
    log_info "API 文档: http://localhost:8000/docs"
}

# 停止服务
stop_services() {
    log_info "停止服务..."

    # 停止后端
    if [ -f "$BACKEND_DIR/backend.pid" ]; then
        kill $(cat "$BACKEND_DIR/backend.pid") 2>/dev/null || true
        rm "$BACKEND_DIR/backend.pid"
        log_info "后端已停止"
    fi

    # 停止前端
    if [ -f "$FRONTEND_DIR/frontend.pid" ]; then
        kill $(cat "$FRONTEND_DIR/frontend.pid") 2>/dev/null || true
        rm "$FRONTEND_DIR/frontend.pid"
        log_info "前端已停止"
    fi
}

# 更新代码
update_code() {
    log_info "更新代码..."
    cd "$PROJECT_DIR"

    git pull origin main

    # 重新安装依赖
    setup_backend
    setup_frontend

    log_info "代码已更新"
}

# 主函数
main() {
    case "${1:-start}" in
        start)
            check_deps
            setup_backend
            setup_frontend
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            sleep 2
            start_services
            ;;
        update)
            stop_services
            update_code
            start_services
            ;;
        *)
            echo "使用方法: $0 [start|stop|restart|update]"
            exit 1
            ;;
    esac
}

main "$@"
