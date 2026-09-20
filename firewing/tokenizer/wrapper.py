"""Thin wrapper around the upstream Qwen3-Omni tokenizer.

Keeping this as its own module means the rest of FIREWING (inference
engine, context manager) depends on a small stable interface
(`encode`, `decode`, `apply_chat_template`, `count_tokens`) rather than
directly on `transformers` internals — so swapping tokenizer libraries
later only touches this one file.
"""

from __future__ import annotations

import inspect

from firewing.inference.tools import render_tools_for_prompt


class TokenizerWrapper:
    def __init__(self, hf_tokenizer):
        self._tok = hf_tokenizer

    def encode(self, text: str) -> list[int]:
        return self._tok.encode(text)

    def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
        return self._tok.decode(token_ids, skip_special_tokens=skip_special_tokens)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def apply_chat_template(
        self,
        messages: list[dict],
        add_generation_prompt: bool = True,
        tools: list[dict] | None = None,
    ) -> str:
        """Render a list of {"role", "content"} messages using the
        upstream chat template, falling back to a plain format if the
        tokenizer doesn't ship one (defensive — keeps FIREWING usable
        even against a base model without a chat template configured).

        If `tools` is given, passes it through to the underlying
        `apply_chat_template(tools=...)` when that's supported
        (Qwen's template supports this natively); otherwise falls back
        to prepending a rendered tool list to the system message so
        tool calling still works with older tokenizer/template
        versions.
        """
        has_native_template = hasattr(self._tok, "apply_chat_template") and getattr(
            self._tok, "chat_template", None
        )

        if has_native_template:
            kwargs = {"tokenize": False, "add_generation_prompt": add_generation_prompt}
            if tools:
                sig = inspect.signature(self._tok.apply_chat_template)
                if "tools" in sig.parameters:
                    kwargs["tools"] = tools
                else:
                    messages = self._inject_tools_into_system(messages, tools)
            return self._tok.apply_chat_template(messages, **kwargs)

        if tools:
            messages = self._inject_tools_into_system(messages, tools)
        parts = [f"{m['role']}: {m['content']}" for m in messages]
        if add_generation_prompt:
            parts.append("assistant:")
        return "\n".join(parts)

    @staticmethod
    def _inject_tools_into_system(messages: list[dict], tools: list[dict]) -> list[dict]:
        tool_text = render_tools_for_prompt(tools)
        messages = [dict(m) for m in messages]  # shallow copy, don't mutate caller's list
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] = f"{messages[0]['content']}\n\n{tool_text}"
        else:
            messages.insert(0, {"role": "system", "content": tool_text})
        return messages
