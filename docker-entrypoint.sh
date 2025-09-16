#!/bin/bash
set -e

# 函数：打印日志
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# 函数：安装运行时依赖
install_runtime_dependencies() {
    log "检查并安装运行时依赖..."
    
    # 检查是否需要安装新的依赖
    local requirements_file="requirements.txt"
    local installed_packages_file="/tmp/installed_packages.txt"
    
    # 如果requirements.txt存在且比已安装包列表新，则重新安装
    if [ -f "$requirements_file" ]; then
        if [ ! -f "$installed_packages_file" ] || [ "$requirements_file" -nt "$installed_packages_file" ]; then
            log "发现新的依赖需求，开始安装..."
            
            # 尝试使用sudo安装，如果失败则使用用户级安装
            if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
                log "尝试使用sudo安装依赖..."
                sudo pip install --no-cache-dir -r "$requirements_file" 2>&1 | while read line; do
                    log "pip: $line"
                done
                INSTALL_RESULT=${PIPESTATUS[0]}
            else
                INSTALL_RESULT=1  # 设置为失败，触发用户级安装
            fi
            
            # 如果sudo安装失败，尝试用户级安装
            if [ $INSTALL_RESULT -ne 0 ]; then
                log "尝试用户级安装依赖..."
                pip install --user --no-cache-dir -r "$requirements_file" 2>&1 | while read line; do
                    log "pip: $line"
                done
                
                # 确保用户级安装的包在PATH中
                export PATH="$HOME/.local/bin:$PATH"
            fi
            
            # 单独安装腾讯云SDK（确保安装）
            log "确保腾讯云SDK已安装..."
            if ! pip list | grep -q "tencentcloud-sdk-python"; then
                log "安装腾讯云SDK..."
                pip install --user tencentcloud-sdk-python>=3.0.1200
            else
                log "腾讯云SDK已安装"
            fi
            
            # 记录安装时间
            touch "$installed_packages_file"
            log "依赖安装完成"
        else
            log "依赖已是最新版本，跳过安装"
        fi
    else
        log "未找到 requirements.txt 文件"
    fi
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
    
    # 安装运行时依赖
    install_runtime_dependencies

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