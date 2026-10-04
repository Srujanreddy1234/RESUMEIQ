# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY resumeiq ./resumeiq
COPY migrations ./migrations
COPY wsgi.py gunicorn.conf.py deploy/entrypoint.sh ./

# Run as an unprivileged user; uploads live in a volume outside the code/static tree.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data/uploads && chown -R app:app /data && chmod 700 /data/uploads \
 && chmod +x entrypoint.sh
USER app

ENV APP_ENV=production STORAGE_DIR=/data/uploads PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)"
ENTRYPOINT ["./entrypoint.sh"]
