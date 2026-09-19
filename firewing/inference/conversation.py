"""Conversation and context management.

Owns multi-turn message history and enforces the configured context
budget by trimming oldest non-system turns first when a conversation
grows past `max_context_tokens`. This is intentionally simple (no
summarization) for the beta — see docs/troubleshooting.md for the
known limitation and planned improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)
    system_prompt: str | None = None

    def add_user(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))

    def to_chat_messages(self) -> list[dict]:
        out: list[dict] = []
        if self.system_prompt:
            out.append({"role": "system", "content": self.system_prompt})
        out.extend({"role": m.role, "content": m.content} for m in self.messages)
        return out

    def trim_to_budget(self, count_tokens_fn, max_tokens: int) -> None:
        """Drop oldest user/assistant turns until the rendered history
        fits under `max_tokens`. The system prompt is never dropped.
        """
        while self.messages:
            rendered = "\n".join(m.content for m in self.messages)
            system_len = count_tokens_fn(self.system_prompt) if self.system_prompt else 0
            if count_tokens_fn(rendered) + system_len <= max_tokens:
                break
            # Drop oldest pair (user + its assistant reply) to keep turns aligned.
            self.messages.pop(0)
