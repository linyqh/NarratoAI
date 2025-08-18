#!/bin/bash
set -e

# 函数：打印日志
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# 函数：检查必要的文件和目录
check_requirements() {
    log "检查应用环境..."

    # 检查配置文件
    if [ ! -f "config.toml" ]; then
        if [ -f "config.example.toml" ]; then
            log "复制示例配置文件..."
            cp config.example.toml config.toml
        else
            log "警告: 未找到配置文件"
        fi
    fi

    # 检查必要的目录
    for dir in "storage/temp" "storage/tasks" "storage/json" "storage/narration_scripts" "storage/drama_analysis"; do
        if [ ! -d "$dir" ]; then
            log "创建目录: $dir"
            mkdir -p "$dir"
        fi
    done

    log "环境检查完成"
}

# 函数：启动 WebUI
start_webui() {
    log "启动 NarratoAI WebUI..."

    # 检查端口是否可用
    if command -v netstat >/dev/null 2>&1; then
        if netstat -tuln | grep -q ":8501 "; then
            log "警告: 端口 8501 已被占用"
        fi
    fi

    # 启动 Streamlit 应用
    exec streamlit run webui.py \
        --server.address=0.0.0.0 \
        --server.port=8501 \
        --server.enableCORS=true \
        --server.maxUploadSize=2048 \
        --server.enableXsrfProtection=false \
        --browser.gatherUsageStats=false \
        --browser.serverAddress=0.0.0.0 \
        --logger.level=info
}

# 主逻辑
log "NarratoAI Docker 容器启动中..."

# 检查环境
check_requirements

# 根据参数执行不同的命令
case "$1" in
    "webui"|"")
        start_webui
        ;;
    "bash"|"sh")
        log "启动交互式 shell..."
        exec /bin/bash
        ;;
    "health")
        # 健康检查命令
        log "执行健康检查..."
        if curl -f http://localhost:8501/_stcore/health >/dev/null 2>&1; then
            log "健康检查通过"
            exit 0
        else
            log "健康检查失败"
            exit 1
        fi
        ;;
    *)
        log "执行自定义命令: $*"
        exec "$@"
        ;;
esac