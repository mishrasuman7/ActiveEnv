# ActiveEnv backend — runs on Alibaba Cloud ECS (Singapore).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg + general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Default: run the API. The Celery worker overrides the command in compose.
CMD ["gunicorn", "activeenv.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
