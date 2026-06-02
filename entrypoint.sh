#!/usr/bin/env bash
set -e

PORT="${PORT:-8080}"
WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${WEB_THREADS:-4}"

echo "[AubeVideo] Migration du schéma (idempotent)…"
# Réessaie quelques fois : la base managée peut mettre quelques secondes à accepter les connexions.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if python -c "from db import init_db; init_db()" 2>/tmp/migrate.err; then
    echo "[AubeVideo] Schéma OK."
    break
  fi
  echo "[AubeVideo] DB pas prête (tentative $i/10)… $(tail -n1 /tmp/migrate.err)"
  sleep 3
done

echo "[AubeVideo] Démarrage gunicorn sur :$PORT ($WORKERS workers × $THREADS threads)…"
exec gunicorn app:app \
  --bind "0.0.0.0:$PORT" \
  --workers "$WORKERS" \
  --threads "$THREADS" \
  --worker-class gthread \
  --timeout 600 \
  --access-logfile - \
  --error-logfile -
