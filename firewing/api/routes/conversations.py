"""Persistent conversation API.

Lets a client create a conversation once, then continue it across
requests without resending the full message history each time — the
server holds the state (see conversation_store.py).

    POST   /v1/conversations                 create a new conversation
    GET    /v1/conversations                 list recent conversations
    GET    /v1/conversations/{id}             fetch one, with messages
    POST   /v1/conversations/{id}/messages    add a user message + get a reply
    DELETE /v1/conversations/{id}             delete a conversation
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from firewing.api.schemas.chat import ChatMessage, ToolCallOut
from firewing.api.security.auth import require_api_key
from firewing.inference.conversation import Conversation
from firewing.inference.engine import GenerationParams
from firewing.inference.multimodal import MultimodalError
from firewing.inference.personas import load_personas
from firewing.utils.logging import get_logger

router = APIRouter(prefix="/v1/conversations")
logger = get_logger("api.conversations")


class CreateConversationRequest(BaseModel):
    title: str = "New conversation"
    persona: str | None = None


class AddMessageRequest(BaseModel):
    message: ChatMessage
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024


@router.post("")
def create_conversation(
    body: CreateConversationRequest, request: Request, _: str = Depends(require_api_key)
):
    store = request.app.state.conversation_store
    record = store.create(title=body.title)
    return record.to_public_dict()


@router.get("")
def list_conversations(request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    return {"conversations": [r.to_public_dict(include_messages=False) for r in store.list()]}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    record = store.get(conversation_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return record.to_public_dict()


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, _: str = Depends(require_api_key)):
    store = request.app.state.conversation_store
    if not store.delete(conversation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"conversation_id": conversation_id, "deleted": True}


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
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Model is not loaded yet"
        )

    persona = load_personas().get("default")
    conversation = Conversation(system_prompt=persona.system_prompt)
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

    try:
        result = engine.generate(conversation, params)
    except MultimodalError as exc:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        stats.record((time.perf_counter() - start_time) * 1000, "error")
        raise

    store.append_message(conversation_id, "assistant", result.text)
    stats.record((time.perf_counter() - start_time) * 1000, "success")

    return {
        "conversation_id": conversation_id,
        "message": {"role": "assistant", "content": result.text},
        "finish_reason": result.finish_reason,
    }
