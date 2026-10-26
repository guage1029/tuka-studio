FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TMPDIR=/tmp XDG_CACHE_HOME=/tmp/cache METRICS_DB=/data/metrics.sqlite3 TRUST_LOCAL_PROXY=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && useradd --uid 10001 --create-home tuka \
    && mkdir /data && chown tuka:tuka /data
COPY app.py main.py ai_providers.py safe_http.py metrics.py ./
COPY template*.html ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY licenses/ ./licenses/
USER tuka
EXPOSE 5001
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--worker-class", "gthread", "--threads", "8", "--timeout", "120", "--access-logfile", "/dev/null", "--error-logfile", "-", "--log-level", "critical", "app:app"]
