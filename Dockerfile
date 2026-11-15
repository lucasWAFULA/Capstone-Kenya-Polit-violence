FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY src ./src
COPY artifacts/production ./artifacts/production
COPY artifacts/forecasting ./artifacts/forecasting
COPY artifacts/data_quality ./artifacts/data_quality
COPY scripts/update_forecasts.py ./scripts/update_forecasts.py
COPY scripts/ingestion_worker.py ./scripts/ingestion_worker.py

RUN mkdir -p /app/runtime /app/data && chown 65532:65532 /app/runtime /app/data

USER 65532:65532
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn severity_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-1}"]
