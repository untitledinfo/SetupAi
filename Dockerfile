# FIREWING 1.0 BETA — API server image.
# For GPU use, run with `docker run --gpus all ...` or the `gpu` service
# in docker-compose.yml, and ensure nvidia-container-toolkit is installed
# on the host.

FROM python:3.11-slim AS base

RUN useradd --system --create-home --shell /usr/sbin/nologin firewing

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /var/log/firewing /var/lib/firewing \
    && chown -R firewing:firewing /app /var/log/firewing /var/lib/firewing

USER firewing

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "firewing.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
