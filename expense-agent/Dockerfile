FROM python:3.11-slim

# HEIC 지원을 위한 시스템 라이브러리
RUN apt-get update && apt-get install -y \
    libheif-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/expense-agent /app/logs

RUN useradd -m appuser && chown -R appuser:appuser /app /tmp/expense-agent
USER appuser

CMD ["python", "main.py"]
