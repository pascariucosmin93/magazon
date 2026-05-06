FROM python:3.12-slim

WORKDIR /app
COPY shared /app/shared
COPY services/payment-service /app/services/payment-service

RUN pip install --no-cache-dir -r /app/services/payment-service/requirements.txt

ENV PYTHONPATH=/app
ENV SERVICE_NAME=payment-service
ENV SERVICE_PORT=8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/services/payment-service", "--host", "0.0.0.0", "--port", "8000"]
