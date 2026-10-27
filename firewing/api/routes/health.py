from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from firewing import __version__, MODEL_NAME, UPSTREAM_BASE_MODEL
from firewing.api.security.auth import require_api_key
from firewing.utils.system_info import get_system_info

router = APIRouter()


@router.get("/health")
def health(request: Request):
    """Unauthenticated liveness check — used by Docker/systemd/nginx."""
    engine = getattr(request.app.state, "engine", None)
    return {
        "status": "ok",
        "version": __version__,
        "model_loaded": engine is not None,
    }


@router.get("/ready")
def ready(request: Request):
    """Readiness probe: returns 200 OK only when the model engine is loaded."""
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model engine is not ready",
        )
    settings = getattr(request.app.state, "settings", None)
    model_path = settings.model.model_path if settings else UPSTREAM_BASE_MODEL
    return {
        "status": "ready",
        "model": model_path,
        "version": __version__,
    }


@router.get("/v1/models")
def list_models(request: Request):
    settings = getattr(request.app.state, "settings", None)
    model_path = settings.model.model_path if settings else UPSTREAM_BASE_MODEL
    adapter_path = settings.model.adapter_path if settings else None
    return {
        "object": "list",
        "data": [
            {
                "id": "firewing-1.0-beta",
                "object": "model",
                "created": 1700000000,
                "owned_by": "setup-ai",
                "base_model": model_path,
                "adapter": adapter_path,
                "multimodal": settings.model.enable_multimodal if settings else True,
                "max_context_tokens": settings.model.max_context_tokens if settings else 32768,
            },
            {
                "id": model_path,
                "object": "model",
                "created": 1700000000,
                "owned_by": "upstream",
                "base_model": model_path,
            },
        ],
    }


@router.get("/v1/system")
def system_info(_: str = Depends(require_api_key)):
    """Authenticated — hardware/runtime details shouldn't be public."""
    info = get_system_info()
    return info.to_dict()


@router.get("/v1/status")
def server_status(request: Request, _: str = Depends(require_api_key)):
    engine = getattr(request.app.state, "engine", None)
    settings = getattr(request.app.state, "settings", None)
    return {
        "model": MODEL_NAME,
        "model_path": settings.model.model_path if settings else UPSTREAM_BASE_MODEL,
        "version": __version__,
        "status": "ready" if engine is not None else "loading",
        "multimodal": settings.model.enable_multimodal if settings else True,
        "tool_calling": settings.model.enable_tool_calling if settings else True,
    }
