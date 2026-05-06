FROM python:3.12-slim

WORKDIR /app
COPY shared /app/shared
COPY services/order-service /app/services/order-service

RUN pip install --no-cache-dir -r /app/services/order-service/requirements.txt

ENV PYTHONPATH=/app
ENV SERVICE_NAME=order-service
ENV SERVICE_PORT=8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/services/order-service", "--host", "0.0.0.0", "--port", "8000"]
