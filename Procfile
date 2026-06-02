web: gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers ${WEB_CONCURRENCY:-2} --threads ${WEB_THREADS:-4} --worker-class gthread --timeout 600
release: python -c "from db import init_db; init_db()"
