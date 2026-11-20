FROM python:3.13.12-slim@sha256:8bc60ca09afaa8ea0d6d1220bde073bacfedd66a4bf8129cbdc8ef0e16c8a952

WORKDIR /app

# Install system dependencies and poetry in one optimized layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    unixodbc \
    unixodbc-dev \
    exiftool \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && pip install --no-cache-dir "poetry==2.3.2"

# Configure poetry for Docker environment
RUN poetry config virtualenvs.create false \
    && poetry config virtualenvs.in-project false \
    && poetry config cache-dir /opt/poetry-cache

# Copy poetry files first for better layer caching
COPY pyproject.toml poetry.lock ./

# Install dependencies with cache mount.
# Gooclaim: --compile ships the libraries as bytecode. Without it, and with
# PYTHONDONTWRITEBYTECODE=1 below, every start re-compiled every module it imported
# (15,649 .py files, 1,304 compiled, measured on dev 2026-11-20): a slow start AND a
# slow first search, since some libraries load on their first use.
RUN poetry install --only=main --no-interaction --no-ansi --no-root --compile

# Copy entrypoint script with proper permissions
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh

# Copy application code (and ship it compiled too — see the install step above)
COPY . .
RUN python -m compileall -q /app/airweave

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/root/.local/bin:$PATH"

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
