# 多阶段构建 - 构建阶段
FROM python:3.12-slim-bookworm AS builder

# 设置构建参数
ARG DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /build

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    git-lfs \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip 并创建虚拟环境
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m venv /opt/venv

# 激活虚拟环境
ENV PATH="/opt/venv/bin:$PATH"

# 复制 requirements.txt 并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.12-slim-bookworm

# 设置运行参数
ARG DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /NarratoAI

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 设置环境变量
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/NarratoAI" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    imagemagick \
    ffmpeg \
    wget \
    curl \
    git-lfs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 配置 ImageMagick 策略（允许处理更多格式）
RUN sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<policy domain="path" rights="read|write" pattern="@\*"/' /etc/ImageMagick-6/policy.xml || true

# 初始化 git-lfs
RUN git lfs install

# 创建非 root 用户（安全最佳实践）
RUN groupadd -r narratoai && useradd -r -g narratoai -d /NarratoAI -s /bin/bash narratoai

# 复制应用代码
COPY --chown=narratoai:narratoai . .

# 确保配置文件存在
RUN if [ ! -f config.toml ]; then cp config.example.toml config.toml; fi

# 创建必要的目录并设置权限
RUN mkdir -p storage/temp storage/tasks storage/json storage/narration_scripts storage/drama_analysis && \
    chown -R narratoai:narratoai /NarratoAI && \
    chmod -R 755 /NarratoAI

# 复制并设置入口点脚本
COPY --chown=narratoai:narratoai docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 切换到非 root 用户
USER narratoai

# 暴露端口
EXPOSE 8501

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 设置入口点
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["webui"]
