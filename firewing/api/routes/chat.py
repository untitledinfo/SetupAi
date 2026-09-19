from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from firewing.api.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
)
from firewing.api.security.auth import require_api_key
from firewing.inference.conversation import Conversation
from firewing.inference.engine import GenerationParams
from firewing.inference.personas import load_personas
from firewing.utils.logging import get_logger

router = APIRouter()
logger = get_logger("api.chat")


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
):
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    start_time = time.perf_counter()
    stats = request.app.state.stats_tracker
    limiter = request.app.state.rate_limiter
    limiter.check(api_key)

    if body.max_tokens > request.app.state.settings.api.max_tokens_per_request:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"max_tokens={body.max_tokens} exceeds server limit "
                f"({request.app.state.settings.api.max_tokens_per_request})"
            ),
        )

    engine = request.app.state.engine
    if engine is None:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not loaded yet",
        )

    personas = load_personas()
    persona = personas.get(body.persona or "default", personas["default"])

    conversation = Conversation(system_prompt=persona.system_prompt)
    for m in body.messages:
        if m.role == "user":
            conversation.add_user(m.content)
        elif m.role == "assistant":
            conversation.add_assistant(m.content)
        # explicit "system" messages in the request override the persona
        elif m.role == "system":
            conversation.system_prompt = m.content

    params = GenerationParams(
        temperature=body.temperature, top_p=body.top_p, max_tokens=body.max_tokens
    )

    logger.info("chat request_id=%s stream=%s persona=%s", request_id, body.stream, persona.name)

    if body.stream:
        def event_stream():
            try:
                for chunk in engine.stream(conversation, params):
                    yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"
                stats.record((time.perf_counter() - start_time) * 1000, "success")
            except Exception:
                stats.record((time.perf_counter() - start_time) * 1000, "error")
                raise

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        text = engine.generate(conversation, params)
    except Exception:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise

    stats.record((time.perf_counter() - start_time) * 1000, "success")
    return ChatCompletionResponse(
        id=request_id,
        model=body.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=text),
                finish_reason="stop",
            )
        ],
    )
