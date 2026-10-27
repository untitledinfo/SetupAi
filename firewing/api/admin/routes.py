"""Admin API — API key management and aggregate request stats.

All routes here require FIREWING_ADMIN_KEY (see security/auth.py's
require_admin_key), which is deliberately separate from regular chat
API keys.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from firewing.api.security.auth import require_admin_key

router = APIRouter(prefix="/v1/admin")


class CreateKeyRequest(BaseModel):
    label: str


class UpdateKeyRequest(BaseModel):
    label: str


@router.post("/keys")
def create_key(
    body: CreateKeyRequest, request: Request, _: str = Depends(require_admin_key)
):
    key_store = request.app.state.key_store
    plaintext, record = key_store.create_key(body.label)
    return {
        # Shown exactly once — the store never persists the plaintext.
        "api_key": plaintext,
        **record.to_public_dict(),
    }


@router.get("/keys")
def list_keys(request: Request, _: str = Depends(require_admin_key)):
    key_store = request.app.state.key_store
    return {"keys": [r.to_public_dict() for r in key_store.list_keys()]}


@router.patch("/keys/{key_id}")
def update_key(
    key_id: str,
    body: UpdateKeyRequest,
    request: Request,
    _: str = Depends(require_admin_key),
):
    key_store = request.app.state.key_store
    if not key_store.update_key(key_id, body.label):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    record = key_store.get_key(key_id)
    return record.to_public_dict() if record else {"key_id": key_id, "updated": True}


@router.delete("/keys/{key_id}")
def revoke_or_delete_key(
    key_id: str,
    request: Request,
    permanent: bool = Query(default=False),
    _: str = Depends(require_admin_key),
):
    key_store = request.app.state.key_store
    if permanent:
        if not key_store.delete_key(key_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
        return {"key_id": key_id, "deleted": True}
    if not key_store.revoke_key(key_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return {"key_id": key_id, "revoked": True}


@router.get("/stats")
def request_stats(request: Request, _: str = Depends(require_admin_key)):
    tracker = request.app.state.stats_tracker
    return tracker.snapshot()
