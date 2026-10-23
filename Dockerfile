# SAHAM server image: engine (FastAPI + auto-scanner + Telegram bot) serving the built UI.
# Build & run: see docs/DEPLOY_LINUX.md  (docker compose up -d --build)

# ── 1. UI build ──────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS ui
WORKDIR /src/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# ── 2. Engine ────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SAHAM_SERVER_MODE=1 \
    SAHAM_DB_PATH=/data/saham.db \
    XDG_CACHE_HOME=/data/.cache \
    TZ=Asia/Jakarta
WORKDIR /app
COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt
COPY engine/ engine/
COPY --from=ui /src/ui/dist ui/dist
RUN useradd --system --uid 1000 --home-dir /app saham && mkdir -p /data && chown saham:saham /data
USER saham
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
# One worker only: the scanner and the bot are background threads and SQLite has one writer
CMD ["python", "-m", "uvicorn", "engine.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
