FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY src ./src
COPY artifacts/production ./artifacts/production

USER 65532:65532
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn severity_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-1}"]
