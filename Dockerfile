# syntax=docker/dockerfile:1
# Pure Flask/gunicorn — Debian slim is appropriate (no Chromium/native compile).
FROM python:3.12-slim@sha256:646fb0bca3dd3ea1bcc6feb72c17ed16eed6e10cffc732fcc1478bd3e7f02d7b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CACHE_DIR=/data/cache \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# -l avoids oversized sparse lastlog with high UIDs
RUN useradd -l --create-home --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY --chown=appuser:appuser app.py cache.py strava.py ./
COPY --chown=appuser:appuser templates ./templates
COPY --chown=appuser:appuser static ./static

RUN mkdir -p /data/cache && chown -R appuser:appuser /app /data/cache

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30", "app:app"]
