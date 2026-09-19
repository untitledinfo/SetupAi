from __future__ import annotations

from fastapi import APIRouter, Depends

from firewing import __version__, MODEL_NAME, UPSTREAM_BASE_MODEL
from firewing.api.security.auth import require_api_key
from firewing.utils.system_info import get_system_info

router = APIRouter()


@router.get("/health")
def health():
    """Unauthenticated liveness check — used by Docker/systemd/nginx."""
    return {"status": "ok", "version": __version__}


@router.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "firewing-1.0-beta",
                "object": "model",
                "owned_by": "setup-ai",
                "base_model": UPSTREAM_BASE_MODEL,
            }
        ],
    }


@router.get("/v1/system")
def system_info(_: str = Depends(require_api_key)):
    """Authenticated — hardware/runtime details shouldn't be public."""
    info = get_system_info()
    return info.to_dict()


@router.get("/v1/status")
def status(_: str = Depends(require_api_key)):
    return {"model": MODEL_NAME, "version": __version__, "status": "running"}
