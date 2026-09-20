from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, Field


class ContentPart(BaseModel):
    """OpenAI-style content part, for multimodal messages."""
    type: str  # "text" | "image_url"
    text: str | None = None
    image_url: dict | None = None  # {"url": "data:..." | "https://..."}


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: Union[str, list[ContentPart], None] = None
    tool_call_id: str | None = None  # required when role == "tool"
    name: str | None = None  # tool name, set when role == "tool"
    tool_calls: list[dict] | None = None  # set on assistant messages that called a tool


class ToolFunctionDef(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolDef(BaseModel):
    type: str = "function"
    function: ToolFunctionDef


class ChatCompletionRequest(BaseModel):
    model: str = "firewing-1.0-beta"
    messages: list[ChatMessage]
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    stream: bool = False
    persona: str | None = None
    tools: list[ToolDef] | None = None
    tool_choice: str | None = None  # "auto" | "none" — advisory in this beta


class ToolCallOut(BaseModel):
    id: str
    type: str = "function"
    function: dict  # {"name": ..., "arguments": "<json string>"}


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[ChatCompletionChoice]


class ErrorDetail(BaseModel):
    type: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
