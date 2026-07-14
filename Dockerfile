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

# 安装 uv 并创建构建虚拟环境
RUN python -m pip install --upgrade pip setuptools wheel uv

# 让 uv 将项目依赖同步到运行阶段复用的虚拟环境
ENV UV_PROJECT_ENVIRONMENT="/opt/venv" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# 复制 uv 项目文件并安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

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

# 一次性安装所有依赖、创建用户、配置系统，减少层级
RUN apt-get update && apt-get install -y --no-install-recommends \
    imagemagick \
    ffmpeg \
    git-lfs \
    ca-certificates \
    && sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<policy domain="path" rights="read|write" pattern="@\*"/' /etc/ImageMagick-6/policy.xml || true \
    && git lfs install \
    && groupadd -r narratoai && useradd -r -g narratoai -d /NarratoAI -s /bin/bash narratoai \
    && rm -rf /var/lib/apt/lists/*

# 复制其余的应用代码
COPY --chown=narratoai:narratoai . .

# 创建核心服务需要的运行时目录
RUN mkdir -p storage/temp storage/tasks storage/json storage/narration_scripts storage/drama_analysis && \
    chown -R narratoai:narratoai /NarratoAI

# 切换到非 root 用户
USER narratoai

# 默认只执行核心层自检；接入新的 API/前端后可覆盖该命令。
CMD ["python", "-m", "app"]
