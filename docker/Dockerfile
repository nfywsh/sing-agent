FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制源代码（保持模块结构）
COPY src/ ./src/
COPY tests/ ./tests/
COPY doc/ ./doc/

# 创建输出目录
RUN mkdir -p /data/voice-temp/output

# 设置 PYTHONPATH，让模块可以正常导入
ENV PYTHONPATH=/app/src

# 暴露端口
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "src.api_server:app", "--host", "0.0.0.0", "--port", "8080"]