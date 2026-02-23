FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码（不复制 data/ 和 venv/，由 volume 提供 data/）
COPY src/ ./src/
COPY tools/ ./tools/

# 确保 data/ 目录存在（volume 挂载时覆盖）
RUN mkdir -p data/raw

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
