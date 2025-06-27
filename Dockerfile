# =====================
# 构建阶段
# =====================
FROM python:3.13-slim-bookworm AS builder
WORKDIR /build

# 更新索引并安装所有构建依赖
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      git-lfs \
      build-essential \
      libffi-dev \
      libssl-dev \
 && git lfs install \
 && rm -rf /var/lib/apt/lists/*

# 创建并激活虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# =====================
# 运行阶段
# =====================
FROM python:3.13-slim-bookworm
WORKDIR /NarratoAI

# 复制并设置虚拟环境所有权
COPY --from=builder /opt/venv /opt/venv

# 复制应用代码并把 /NarratoAI 归属给非 root 用户
COPY . /NarratoAI

# 安装运行时依赖（ImageMagick、FFmpeg、Git LFS 等）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      imagemagick \
      ffmpeg \
      wget \
      git-lfs \
 && sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml \
 && git lfs install \
 && rm -rf /var/lib/apt/lists/*

# 环境变量
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/NarratoAI" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

    # 暴露端口并设置入口
EXPOSE 8501
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh



# 创建非 root 用户并切换（固定 UID=1000，GID=1000，方便文件同步）
RUN groupadd --system --gid 1000 appgroup \
 && useradd --system --uid 1000 --gid 1000 --create-home appuser


# 在切换到非 root 用户前创建并授权所需目录
RUN mkdir -p /NarratoAI/storage/temp/merge \
    /NarratoAI/resource/videos \
    /NarratoAI/resource/srt \
 && chown -R appuser:appgroup /NarratoAI/storage /NarratoAI/resource

USER appuser


ENTRYPOINT ["docker-entrypoint.sh"]