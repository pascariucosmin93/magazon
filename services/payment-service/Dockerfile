# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
COPY services/payment-service/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false app

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/alembic
COPY shared /app/shared
COPY services/payment-service /app/services/payment-service

ENV PYTHONPATH=/app
ENV SERVICE_NAME=payment-service
ENV SERVICE_PORT=8000
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/services/payment-service", "--host", "0.0.0.0", "--port", "8000"]
