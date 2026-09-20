"""Conversation and context management.

Owns multi-turn message history and enforces the configured context
budget by trimming oldest non-system turns first when a conversation
grows past `max_context_tokens` (see context.py for the "summarize
instead of drop" alternative strategy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def content_to_text(content: Any) -> str:
    """Best-effort plain-text rendering of a message's content, for
    token counting and budget trimming. Multimodal messages (content
    as a list of parts) only contribute their text parts here — images
    aren't counted against the text token budget.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
    return str(content)


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: Any  # str, or a list of OpenAI-style content parts (text/image_url)
    tool_call_id: str | None = None  # set on role="tool" messages
    name: str | None = None  # tool name, set on role="tool" messages


@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)
    system_prompt: str | None = None

    def add_user(self, content: Any) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: Any) -> None:
        self.messages.append(Message(role="assistant", content=content))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append(
            Message(role="tool", content=content, tool_call_id=tool_call_id, name=name)
        )

    def to_chat_messages(self) -> list[dict]:
        out: list[dict] = []
        if self.system_prompt:
            out.append({"role": "system", "content": self.system_prompt})
        for m in self.messages:
            entry: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                entry["tool_call_id"] = m.tool_call_id
            if m.name:
                entry["name"] = m.name
            out.append(entry)
        return out

    def trim_to_budget(self, count_tokens_fn, max_tokens: int) -> None:
        """Drop oldest user/assistant turns until the rendered history
        fits under `max_tokens`. The system prompt is never dropped.
        """
        while self.messages:
            rendered = "\n".join(content_to_text(m.content) for m in self.messages)
            system_len = count_tokens_fn(self.system_prompt) if self.system_prompt else 0
            if count_tokens_fn(rendered) + system_len <= max_tokens:
                break
            # Drop oldest pair (user + its assistant reply) to keep turns aligned.
            self.messages.pop(0)
