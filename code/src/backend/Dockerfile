# MemoryLane API. Build context is code/src (see docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models

WORKDIR /app

# CPU-only torch first, so sentence-transformers doesn't pull the CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ backend/
COPY scripts/ scripts/
COPY evaluation/ evaluation/

# Run as an unprivileged user; /models is a volume so models download once.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /models \
    && chown -R app:app /models /app
USER app
VOLUME /models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# One worker: each worker would load its own copy of the embedding model.
# Sync endpoints run in the thread pool, which handles concurrency.
# Caddy is the only client, so proxy headers are trusted from any address.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
