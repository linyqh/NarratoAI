FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /NarratoAI

# 设置/NarratoAI目录权限为777
RUN chmod 777 /NarratoAI

ENV PYTHONPATH="/NarratoAI"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    imagemagick \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Fix security policy for ImageMagick
RUN sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml

# Copy only the requirements.txt first to leverage Docker cache
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the codebase into the image
COPY . .

# 安装 git lfs 并下载模型到指定目录
RUN git lfs install

# Expose the port the app runs on
EXPOSE 8501

# Command to run the application
CMD ["streamlit", "run", "webui.py","--browser.serverAddress=127.0.0.1","--server.enableCORS=True","--browser.gatherUsageStats=False"]
