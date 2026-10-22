# Stage 1: build the React SPA
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime serving the API and the SPA from one origin
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static HF_HOME=/app/.cache FASTEMBED_CACHE_PATH=/app/.cache/fastembed
WORKDIR /app
COPY backend/requirements.txt backend/requirements-ml.txt ./
RUN pip install -r requirements.txt -r requirements-ml.txt
COPY backend/ ./
# bake the embedding model into the image so the first request never downloads it
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
COPY --from=web /web/dist /app/static
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
