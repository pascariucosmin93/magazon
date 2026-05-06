FROM python:3.12-slim

WORKDIR /app
COPY shared /app/shared
COPY services/notification-service /app/services/notification-service

RUN pip install --no-cache-dir -r /app/services/notification-service/requirements.txt

ENV PYTHONPATH=/app
ENV SERVICE_NAME=notification-service
ENV SERVICE_PORT=8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/services/notification-service", "--host", "0.0.0.0", "--port", "8000"]
