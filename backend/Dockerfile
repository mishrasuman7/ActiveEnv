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

# Bake admin/DRF static assets into the image (no DB needed for this step).
RUN python manage.py collectstatic --noinput

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health/ || exit 1

# Default: run the API. The Celery worker overrides the command in compose.
CMD ["gunicorn", "activeenv.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
