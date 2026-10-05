FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r /app/backend/requirements.lock
COPY backend /app/backend
COPY workers /app/workers
CMD ["python", "-m", "workers.audio_analysis.worker"]
