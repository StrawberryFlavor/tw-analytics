# 使用Python 3.11官方镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# 安装基础系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 创建非root用户和必要目录
RUN useradd --create-home --shell /bin/bash app && \
    mkdir -p /app/instance && \
    chown -R app:app /app

# 复制应用代码
COPY . .
RUN chown -R app:app /app

# 安装Playwright系统依赖（作为root用户）
RUN playwright install-deps chromium

# 切换到app用户并安装浏览器
USER app
RUN playwright install chromium

# 暴露端口
EXPOSE 5100

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5100/api/v1/health || exit 1

# 启动命令
CMD ["gunicorn", "--config", "docker/gunicorn.conf.py", "wsgi:application"]