FROM python:3.13-alpine AS builder
WORKDIR /build

# 安装依赖并创建用户
RUN apk add --no-cache git git-lfs build-base linux-headers libffi-dev openssl-dev \
 && addgroup -S appgroup \
 && adduser -S -G appgroup appuser \
 && git lfs install

# 虚拟环境与依赖安装
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 运行时镜像
FROM python:3.13-alpine
WORKDIR /NarratoAI

# 复制并设置所有权
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . /NarratoAI

# 安装运行时依赖
RUN apk add --no-cache imagemagick ffmpeg wget git-lfs \
 && sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml \
 && git lfs install

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/NarratoAI" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 切换到非 root 用户
USER appuser

# 暴露端口与入口
EXPOSE 8501
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
