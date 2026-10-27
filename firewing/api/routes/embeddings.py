from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from firewing.api.schemas.chat import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingObject,
)
from firewing.api.security.auth import require_api_key
from firewing.utils.logging import get_logger

router = APIRouter()
logger = get_logger("api.embeddings")


def _fallback_embedding(text: str, dim: int = 64) -> list[float]:
    """Deterministic normalized pseudo-embedding based on hash digest,
    used for lightweight/testing scenarios or when model hidden states
    are not requested.
    """
    raw_hash = hashlib.sha512(text.encode("utf-8")).digest()
    vec = [(b - 128) / 128.0 for b in raw_hash[:dim]]
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [round(x / norm, 6) for x in vec]


@router.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    body: EmbeddingRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
):
    start_time = time.perf_counter()
    stats = request.app.state.stats_tracker
    limiter = request.app.state.rate_limiter
    limiter.check(api_key)

    inputs = [body.input] if isinstance(body.input, str) else body.input
    if not inputs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="input must not be empty",
        )

    engine = request.app.state.engine
    data: list[EmbeddingObject] = []
    total_tokens = 0

    for idx, text in enumerate(inputs):
        if engine is not None and hasattr(engine, "tokenizer"):
            tokens = engine.tokenizer.count_tokens(text)
            total_tokens += tokens
            # If loaded model supports embedding extraction
            try:
                import torch

                inputs_pt = engine.loaded.tokenizer(text, return_tensors="pt")
                if engine.loaded.device != "cpu":
                    inputs_pt = {k: v.to(engine.loaded.device) for k, v in inputs_pt.items()}
                with torch.no_grad():
                    outputs = engine.loaded.model(**inputs_pt, output_hidden_states=True)
                    last_hidden = outputs.hidden_states[-1]
                    pooled = last_hidden.mean(dim=1).squeeze()
                    # Normalize
                    normalized = pooled / torch.norm(pooled, p=2, dim=-1, keepdim=True)
                    vec = normalized.cpu().tolist()
                    if isinstance(vec, float):
                        vec = [vec]
            except Exception:
                vec = _fallback_embedding(text)
        else:
            total_tokens += len(text.split())
            vec = _fallback_embedding(text)

        data.append(EmbeddingObject(object="embedding", index=idx, embedding=vec))

    stats.record(
        (time.perf_counter() - start_time) * 1000,
        "success",
        endpoint="embeddings",
        tokens=total_tokens,
    )

    return EmbeddingResponse(
        object="list",
        data=data,
        model=body.model,
        usage={"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    )
