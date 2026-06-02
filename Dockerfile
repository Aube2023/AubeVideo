# AubeVideo — image de production
FROM python:3.11-slim

# ffmpeg/ffprobe pour miniatures + transcodage ; libpq inutile (psycopg2-binary embarque libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    AUBEVIDEO_BEHIND_PROXY=1 \
    AUBEVIDEO_HTTPS=1 \
    AUBEVIDEO_PAM_LOGIN=0 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Dossier uploads persistant (monter un volume / disque dessus en prod)
RUN mkdir -p /app/uploads /app/logs
VOLUME ["/app/uploads"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
