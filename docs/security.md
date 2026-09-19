# Security

- **No hardcoded secrets.** API keys live in `FIREWING_API_KEYS`
  (env var / `.env` / systemd `EnvironmentFile=`), never in
  `configs/firewing.yaml`.
- **Non-root execution.** The systemd unit runs as the dedicated
  `firewing` user (see `install.sh`); the Docker image runs as a
  non-root `firewing` user too.
- **Input validation.** All API request bodies are validated by
  Pydantic schemas (`firewing/api/schemas/`) before touching the model.
- **Rate limiting.** Per-API-key token bucket
  (`firewing/api/security/rate_limit.py`). In-memory in this beta —
  see `docs/troubleshooting.md` for the multi-replica caveat.
- **Safe logging.** `firewing/utils/logging.redact()` is used anywhere
  a key/token might otherwise reach a log line; only the last few
  characters of a rejected key are ever logged.
- **CORS** is closed by default (`api.cors_allowed_origins: []`) —
  set explicit origins in production, never `*`.
- **HTTPS**: terminate TLS at nginx using Let's Encrypt (see
  `docs/vps.md` and `scripts/deploy/nginx.conf.example`); the FIREWING
  API itself does not speak TLS directly.
- **Required open ports**: SSH, and 80/443 on the nginx host if used.
  The API port itself should stay internal.
- **systemd hardening**: `firewing.service` sets `NoNewPrivileges`,
  `PrivateTmp`, and `ProtectSystem=strict` with explicit
  `ReadWritePaths` for logs/data — review before relaxing.

## Reporting a vulnerability

See `SECURITY.md` at the repo root.
