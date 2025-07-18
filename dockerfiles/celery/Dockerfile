FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CELERY_CONCURRENCY=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        procps \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install poetry flower

WORKDIR /app
ADD pyproject.toml poetry.lock /app/
COPY ./atlas_forge /app/

RUN poetry install --no-root

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD celery -A celery_worker inspect ping || exit 1

# Default command (can be overridden in docker-compose)
ENTRYPOINT ["poetry", "run"]
CMD ["celery", "-A", "atlas_forge.worker", "worker", "--loglevel=info", "--concurrency=2"]