FROM python:3.12-slim

# 不写 .pyc、日志不缓冲，便于容器内观察
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/film.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 数据库文件所在目录，运行时挂载卷持久化
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 启动时由 FastAPI lifespan 自动建库建表，无需额外初始化步骤
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
