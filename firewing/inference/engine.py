"""Inference engine: turns a Conversation into generated text, streaming
or not. This is FIREWING's own code — it wraps the loaded upstream
model with a stable generate()/stream() interface so the API layer and
the CLI don't need to know anything about `transformers` internals.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from firewing.model.loader import LoadedModel
from firewing.tokenizer.wrapper import TokenizerWrapper
from firewing.inference.conversation import Conversation
from firewing.inference.context import trim_by_dropping, trim_by_summarizing
from firewing.inference.tools import ToolCall, extract_tool_calls
from firewing.utils.logging import get_logger

logger = get_logger("inference.engine")


@dataclass
class GenerationParams:
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024


@dataclass
class GenerationResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def finish_reason(self) -> str:
        return "tool_calls" if self.tool_calls else "stop"


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

    def generate(
        self,
        conversation: Conversation,
        params: GenerationParams,
        tools: list[dict] | None = None,
    ) -> GenerationResult:
        """Non-streaming generation — used by /v1/chat/completions when
        stream=false, and always used when `tools` is set (tool-call
        parsing needs the complete response; see docs/tool-calling.md
        for why this beta doesn't support streaming + tools together).
        """
        raw_text = "".join(self.stream(conversation, params, tools=tools))
        if tools:
            text, tool_calls = extract_tool_calls(raw_text)
            return GenerationResult(text=text, tool_calls=tool_calls)
        return GenerationResult(text=raw_text)

    def stream(
        self,
        conversation: Conversation,
        params: GenerationParams,
        tools: list[dict] | None = None,
    ) -> Iterator[str]:
        """Yield text chunks as they're generated.

        Uses `transformers.TextIteratorStreamer` in a background thread
        so callers (sync CLI, async FastAPI endpoint) can consume it as
        a simple iterator either way.

        Note: when `tools` is set, the raw `<tool_call>` tag text is
        still what gets yielded here — tool-call *parsing* only happens
        in generate(), which is why the API route requires
        stream=false whenever tools are provided.
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

        chat_messages = conversation.to_chat_messages()
        images = self._collect_images(conversation)

        import torch
        from transformers import TextIteratorStreamer
        import threading

        use_processor = bool(images) and self.loaded.supports_multimodal
        if images and not self.loaded.supports_multimodal:
            logger.warning(
                "Message includes image content but no multimodal processor is "
                "loaded (model.enable_multimodal may be false, or this checkpoint "
                "doesn't ship one) — ignoring the image(s)."
            )

        if use_processor and hasattr(self.loaded.processor, "apply_chat_template"):
            prompt = self.loaded.processor.apply_chat_template(
                chat_messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.loaded.processor(text=prompt, images=images, return_tensors="pt")
        else:
            prompt = self.tokenizer.apply_chat_template(chat_messages, tools=tools)
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

    @staticmethod
    def _collect_images(conversation: Conversation) -> list:
        """Decode every image_url content part across the conversation,
        in order. Import kept local to avoid pulling Pillow into every
        code path that only ever imports InferenceEngine for text use.
        """
        from firewing.inference.multimodal import parse_content

        images = []
        for message in conversation.messages:
            if isinstance(message.content, list):
                images.extend(parse_content(message.content).images)
        return images

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
