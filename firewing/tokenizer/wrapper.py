"""Thin wrapper around the upstream Qwen3-Omni tokenizer.

Keeping this as its own module means the rest of FIREWING (inference
engine, context manager) depends on a small stable interface
(`encode`, `decode`, `apply_chat_template`, `count_tokens`) rather than
directly on `transformers` internals — so swapping tokenizer libraries
later only touches this one file.
"""

from __future__ import annotations


class TokenizerWrapper:
    def __init__(self, hf_tokenizer):
        self._tok = hf_tokenizer

    def encode(self, text: str) -> list[int]:
        return self._tok.encode(text)

    def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
        return self._tok.decode(token_ids, skip_special_tokens=skip_special_tokens)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def apply_chat_template(self, messages: list[dict], add_generation_prompt: bool = True) -> str:
        """Render a list of {"role", "content"} messages using the
        upstream chat template, falling back to a plain format if the
        tokenizer doesn't ship one (defensive — keeps FIREWING usable
        even against a base model without a chat template configured).
        """
        if hasattr(self._tok, "apply_chat_template") and getattr(
            self._tok, "chat_template", None
        ):
            return self._tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=add_generation_prompt
            )
        parts = [f"{m['role']}: {m['content']}" for m in messages]
        if add_generation_prompt:
            parts.append("assistant:")
        return "\n".join(parts)
