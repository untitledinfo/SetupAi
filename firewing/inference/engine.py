"""Inference engine: turns a Conversation into generated text, streaming
or not. This is FIREWING's own code — it wraps the loaded upstream
model with a stable generate()/stream() interface so the API layer and
the CLI don't need to know anything about `transformers` internals.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from firewing.model.loader import LoadedModel
from firewing.tokenizer.wrapper import TokenizerWrapper
from firewing.inference.conversation import Conversation
from firewing.inference.context import trim_by_dropping, trim_by_summarizing
from firewing.utils.logging import get_logger

logger = get_logger("inference.engine")


@dataclass
class GenerationParams:
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024


class InferenceEngine:
    def __init__(
        self,
        loaded: LoadedModel,
        max_context_tokens: int,
        context_strategy: str = "drop",
    ):
        self.loaded = loaded
        self.tokenizer = TokenizerWrapper(loaded.tokenizer)
        self.max_context_tokens = max_context_tokens
        self.context_strategy = context_strategy

    def generate(self, conversation: Conversation, params: GenerationParams) -> str:
        """Non-streaming generation — used by /v1/chat/completions when
        stream=false and by simple CLI use.
        """
        chunks = list(self.stream(conversation, params))
        return "".join(chunks)

    def stream(self, conversation: Conversation, params: GenerationParams) -> Iterator[str]:
        """Yield text chunks as they're generated.

        Uses `transformers.TextIteratorStreamer` in a background thread
        so callers (sync CLI, async FastAPI endpoint) can consume it as
        a simple iterator either way.
        """
        if self.context_strategy == "summarize":
            trim_by_summarizing(
                conversation,
                self.tokenizer.count_tokens,
                self.max_context_tokens,
                summarizer_fn=lambda text: self._summarize(text),
            )
        else:
            trim_by_dropping(conversation, self.tokenizer.count_tokens, self.max_context_tokens)

        prompt = self.tokenizer.apply_chat_template(conversation.to_chat_messages())

        import torch
        from transformers import TextIteratorStreamer
        import threading

        inputs = self.loaded.tokenizer(prompt, return_tensors="pt")
        if self.loaded.device != "cpu":
            inputs = {k: v.to(self.loaded.device) for k, v in inputs.items()}

        streamer = TextIteratorStreamer(
            self.loaded.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        generation_kwargs = dict(
            **inputs,
            max_new_tokens=params.max_tokens,
            temperature=max(params.temperature, 1e-5),
            top_p=params.top_p,
            do_sample=params.temperature > 0,
            streamer=streamer,
        )

        thread = threading.Thread(target=self.loaded.model.generate, kwargs=generation_kwargs)
        thread.start()

        try:
            for chunk in streamer:
                yield chunk
        finally:
            thread.join(timeout=1)

    def _summarize(self, prompt: str) -> str:
        """Non-streaming, low-token-budget generation used internally
        by the "summarize" context strategy. Deliberately bypasses the
        public stream()/generate() context-trimming path to avoid
        recursive summarization.
        """
        conversation = Conversation(system_prompt="You produce concise, factual summaries.")
        conversation.add_user(prompt)
        rendered = self.tokenizer.apply_chat_template(conversation.to_chat_messages())

        inputs = self.loaded.tokenizer(rendered, return_tensors="pt")
        if self.loaded.device != "cpu":
            inputs = {k: v.to(self.loaded.device) for k, v in inputs.items()}

        output = self.loaded.model.generate(**inputs, max_new_tokens=200, do_sample=False)
        return self.tokenizer.decode(
            output[0][inputs["input_ids"].shape[1]:].tolist(), skip_special_tokens=True
        )
