from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from firewing.api.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    ToolCallOut,
)
from firewing.api.security.auth import require_api_key
from firewing.inference.conversation import Conversation
from firewing.inference.engine import GenerationParams
from firewing.inference.multimodal import MultimodalError
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

    if body.tools and body.stream:
        # Tool-call parsing needs the complete response (see
        # InferenceEngine.stream's docstring) — reject the combination
        # up front with a clear message rather than silently ignoring
        # tool calls embedded in a stream.
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tools + stream=true is not supported in this beta; set stream=false when using tools.",
        )

    personas = load_personas()
    persona = personas.get(body.persona or "default", personas["default"])

    conversation = Conversation(system_prompt=persona.system_prompt)
    try:
        for m in body.messages:
            content = [p.model_dump(exclude_none=True) for p in m.content] if isinstance(m.content, list) else m.content
            if m.role == "user":
                conversation.add_user(content)
            elif m.role == "assistant":
                conversation.add_assistant(content)
            elif m.role == "tool":
                if not m.tool_call_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="role=tool messages require tool_call_id",
                    )
                conversation.add_tool_result(m.tool_call_id, m.name or "", content or "")
            elif m.role == "system":
                # explicit "system" messages in the request override the persona
                conversation.system_prompt = content
    except MultimodalError as exc:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise

    engine = request.app.state.engine
    if engine is None:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not loaded yet",
        )

    params = GenerationParams(
        temperature=body.temperature, top_p=body.top_p, max_tokens=body.max_tokens
    )
    tools = [t.model_dump() for t in body.tools] if body.tools else None

    logger.info(
        "chat request_id=%s stream=%s persona=%s tools=%s",
        request_id, body.stream, persona.name, bool(tools),
    )

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
        result = engine.generate(conversation, params, tools=tools)
    except MultimodalError as exc:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise

    stats.record((time.perf_counter() - start_time) * 1000, "success")

    tool_calls_out = None
    if result.tool_calls:
        tool_calls_out = [
            ToolCallOut(
                id=tc.id,
                function={"name": tc.name, "arguments": json.dumps(tc.arguments)},
            ).model_dump()
            for tc in result.tool_calls
        ]

    return ChatCompletionResponse(
        id=request_id,
        model=body.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=result.text or None,
                    tool_calls=tool_calls_out,
                ),
                finish_reason=result.finish_reason,
            )
        ],
    )
