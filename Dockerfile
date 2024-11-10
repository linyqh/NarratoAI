# 构建阶段
FROM python:3.10-slim-bullseye as builder

# 设置工作目录
WORKDIR /build

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 首先安装 PyTorch（因为它是最大的依赖）
RUN pip install --no-cache-dir torch torchvision torchaudio

# 然后安装其他依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.10-slim-bullseye

# 设置工作目录
WORKDIR /NarratoAI

# 从builder阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    wget \
    git-lfs \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml

# 设置环境变量
ENV PYTHONPATH="/NarratoAI" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 设置目录权限
RUN chmod 777 /NarratoAI

# 安装git lfs
RUN git lfs install

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8501 8080

# 使用脚本作为入口点
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
