# Docker

```bash
cp .env.example .env   # set FIREWING_API_KEYS
docker compose up -d
docker compose logs -f
curl http://localhost:8000/health
```

## GPU passthrough

Requires `nvidia-container-toolkit` on the host. Uncomment the
`deploy.resources.reservations.devices` block in `docker-compose.yml`,
or run directly:

```bash
docker run --gpus all --env-file .env -p 8000:8000 firewing:1.0.0-beta
```

## Persistent data

Two named volumes: `firewing-models` (weight cache) and
`firewing-logs`. `configs/` is bind-mounted read-only so you can edit
`configs/firewing.yaml` on the host without rebuilding the image.

## Health checks

The image defines a `HEALTHCHECK` hitting `/health`; `docker ps` will
show `(healthy)`/`(unhealthy)` once the container has been up longer
than the 60s start period.
