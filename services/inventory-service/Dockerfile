FROM python:3.12-slim

WORKDIR /app
COPY shared /app/shared
COPY services/inventory-service /app/services/inventory-service

RUN pip install --no-cache-dir -r /app/services/inventory-service/requirements.txt

ENV PYTHONPATH=/app
ENV SERVICE_NAME=inventory-service
ENV SERVICE_PORT=8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/services/inventory-service", "--host", "0.0.0.0", "--port", "8000"]
