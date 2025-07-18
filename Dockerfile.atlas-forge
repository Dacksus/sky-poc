FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install poetry

WORKDIR /app
ADD pyproject.toml poetry.lock /app/
COPY ./atlas_forge /app/

RUN poetry install --no-root

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

ENTRYPOINT ["poetry", "run"]
CMD ["uvicorn", "atlas_forge:api", "--host", "0.0.0.0", "--port", "8000", "--reload"]