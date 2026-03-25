FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    apscheduler==3.10.4 \
    httpx==0.27.0 \
    python-dotenv==1.0.1

COPY scheduler.py .

CMD ["python", "-u", "scheduler.py"]
