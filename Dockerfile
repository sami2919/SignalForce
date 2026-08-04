# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No build toolchain on purpose: psycopg[binary] bundles libpq, and selectolax
# ships manylinux wheels. If a future dependency needs compiling, add a builder
# stage rather than shipping gcc in the runtime image.
COPY pyproject.toml ./
COPY scripts/ ./scripts/
RUN pip install --no-cache-dir -e .

COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY config.example/ ./config.example/

# Non-root. A container running as root is one container-escape away from a
# root host process.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "scripts.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
