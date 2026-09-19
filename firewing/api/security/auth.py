"""API key authentication.

Two sources of valid keys, checked together:
  1. FIREWING_API_KEYS env var (comma-separated) — simple, restart-to-change,
     good for a single-operator deployment.
  2. The persistent KeyStore (firewing/api/security/key_store.py) —
     multi-user, addable/revocable via the admin API without a restart.

Failed auth attempts are logged WITHOUT the attempted key — only a
redacted tail — per the "no secrets in logs" rule.

Admin endpoints (key management) use a *separate* key,
FIREWING_ADMIN_KEY, so a regular chat API key can never manage other
users' keys.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, Request, status

from firewing.utils.logging import get_logger, redact

logger = get_logger("api.auth")


def _load_env_keys() -> set[str]:
    raw = os.environ.get("FIREWING_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def require_api_key(
    request: Request, authorization: str | None = Header(default=None)
) -> str:
    """FastAPI dependency: validates `Authorization: Bearer <key>`
    against env-var keys and/or the app's KeyStore (whichever are
    configured). Raises 401 if missing/invalid.
    """
    env_keys = _load_env_keys()
    key_store = getattr(request.app.state, "key_store", None)
    store_has_keys = bool(key_store and key_store.list_keys())

    if not env_keys and not store_has_keys:
        # No keys configured anywhere — for local/dev use only.
        logger.warning("No API keys configured (FIREWING_API_KEYS empty, key store empty)")
        return "unauthenticated-dev-mode"

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    key = authorization.removeprefix("Bearer ").strip()

    if key in env_keys:
        return redact(key)
    if key_store and key_store.is_valid(key):
        return redact(key)

    logger.info("Rejected API key ending in %s", redact(key))
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def require_admin_key(authorization: str | None = Header(default=None)) -> str:
    """Separate, higher-privilege dependency for /v1/admin/* routes.

    Deliberately does NOT accept regular chat API keys — a leaked chat
    key should never be enough to mint or revoke other keys.
    """
    admin_key = os.environ.get("FIREWING_ADMIN_KEY", "").strip()
    if not admin_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is disabled: FIREWING_ADMIN_KEY is not set",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    key = authorization.removeprefix("Bearer ").strip()
    if key != admin_key:
        logger.info("Rejected admin key ending in %s", redact(key))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")

    return redact(key)
