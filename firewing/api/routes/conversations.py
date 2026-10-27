"""Persistent conversation API.

Lets a client create a conversation once, then continue it across
requests without resending the full message history each time — the
server holds the state (see conversation_store.py).

    POST   /v1/conversations                      create a new conversation
    GET    /v1/conversations                      list recent conversations
    GET    /v1/conversations/{id}                  fetch one, with messages
    PATCH  /v1/conversations/{id}                  update title/persona
    POST   /v1/conversations/{id}/messages         add a user message + get a reply (supports stream)
    POST   /v1/conversations/{id}/clear            clear conversation history
    GET    /v1/conversations/{id}/export           export conversation as markdown or JSON
    DELETE /v1/conversations/{id}                  delete a conversation
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from firewing.api.schemas.chat import ChatMessage
from firewing.api.security.auth import require_api_key
from firewing.inference.conversation import Conversation
from firewing.inference.engine import GenerationParams
from firewing.inference.multimodal import MultimodalError
from firewing.inference.personas import DEFAULT_PERSONA, load_personas
from firewing.utils.logging import get_logger

router = APIRouter(prefix="/v1/conversations")
logger = get_logger("api.conversations")


class CreateConversationRequest(BaseModel):
    title: str = "New conversation"
    persona: str | None = None
    system_prompt: str | None = None


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    persona: str | None = None
    system_prompt: str | None = None


class AddMessageRequest(BaseModel):
    message: ChatMessage
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    stream: bool = False


@router.post("")
def create_conversation(
    body: CreateConversationRequest, request: Request, _: str = Depends(require_api_key)
):
    store = request.app.state.conversation_store
    record = store.create(
        title=body.title,
        persona=body.persona,
        system_prompt=body.system_prompt,
    )
    return record.to_public_dict()


@router.get("")
def list_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    _: str = Depends(require_api_key),
):
    store = request.app.state.conversation_store
    return {"conversations": [r.to_public_dict(include_messages=False) for r in store.list(limit=limit)]}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return record.to_public_dict()


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    request: Request,
    _: str = Depends(require_api_key),
):
    store = request.app.state.conversation_store
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    store.update(
        conversation_id,
        title=body.title,
        persona=body.persona,
        system_prompt=body.system_prompt,
    )
    updated = store.get(conversation_id)
    return updated.to_public_dict() if updated else {"conversation_id": conversation_id, "updated": True}


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    if not store.delete(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"conversation_id": conversation_id, "deleted": True}


@router.post("/{conversation_id}/clear")
def clear_conversation(conversation_id: str, request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    store.clear_messages(conversation_id)
    return {"conversation_id": conversation_id, "cleared": True}


@router.get("/{conversation_id}/export")
def export_conversation(
    conversation_id: str,
    request: Request,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    _: str = Depends(require_api_key),
):
    store = request.app.state.conversation_store
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if format == "json":
        return record.to_public_dict(include_messages=True)
    md = store.export_markdown(conversation_id) or ""
    return Response(content=md, media_type="text/markdown")


@router.post("/{conversation_id}/messages")
def add_message(
    conversation_id: str,
    body: AddMessageRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
):
    start_time = time.perf_counter()
    stats = request.app.state.stats_tracker
    store = request.app.state.conversation_store
    limiter = request.app.state.rate_limiter
    limiter.check(api_key)

    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    engine = request.app.state.engine
    if engine is None:
        stats.record((time.perf_counter() - start_time) * 1000, "error", endpoint="conversations")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Model is not loaded yet"
        )

    personas = load_personas()
    persona_name = record.persona or "default"
    persona = personas.get(persona_name, personas.get("default", DEFAULT_PERSONA))
    sys_prompt = record.system_prompt or persona.system_prompt

    conversation = Conversation(system_prompt=sys_prompt)
    for m in record.messages:
        if m.role == "user":
            conversation.add_user(m.content)
        elif m.role == "assistant":
            conversation.add_assistant(m.content)
        elif m.role == "tool":
            conversation.add_tool_result(m.tool_call_id or "", m.name or "", m.content)

    new_content = (
        [p.model_dump(exclude_none=True) for p in body.message.content]
        if isinstance(body.message.content, list)
        else body.message.content
    )
    conversation.add_user(new_content)

    try:
        store.append_message(conversation_id, "user", new_content)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    params = GenerationParams(
        temperature=body.temperature, top_p=body.top_p, max_tokens=body.max_tokens
    )

    if body.stream:
        def event_stream():
            full_reply: list[str] = []
            try:
                for chunk in engine.stream(conversation, params):
                    full_reply.append(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'conversation_id': conversation_id})}\n\n"
                assistant_text = "".join(full_reply)
                store.append_message(conversation_id, "assistant", assistant_text)
                yield f"data: {json.dumps({'content': '', 'conversation_id': conversation_id, 'finish_reason': 'stop'})}\n\n"
                yield "data: [DONE]\n\n"
                stats.record(
                    (time.perf_counter() - start_time) * 1000,
                    "success",
                    endpoint="conversations",
                    tokens=len(assistant_text.split()),
                )
            except Exception:
                stats.record((time.perf_counter() - start_time) * 1000, "error", endpoint="conversations")
                raise

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        result = engine.generate(conversation, params)
    except MultimodalError as exc:
        stats.record((time.perf_counter() - start_time) * 1000, "error", endpoint="conversations")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        stats.record((time.perf_counter() - start_time) * 1000, "error", endpoint="conversations")
        raise

    store.append_message(conversation_id, "assistant", result.text)
    stats.record(
        (time.perf_counter() - start_time) * 1000,
        "success",
        endpoint="conversations",
        tokens=len((result.text or "").split()),
    )

    return {
        "conversation_id": conversation_id,
        "message": {"role": "assistant", "content": result.text},
        "finish_reason": result.finish_reason,
    }
