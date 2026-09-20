# Multimodal Input (Images)

FIREWING accepts image content in chat messages, OpenAI-vision-style:

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
      ]
    }
  ]
}
```

`image_url.url` accepts either an `http(s)://` URL or a `data:` URI
(base64-encoded image), the same two forms OpenAI's API accepts.

## How it works

- At model load time, if `model.enable_multimodal` is true (default),
  FIREWING attempts to load a Hugging Face `AutoProcessor` for the
  configured `model.model_path`.
- If that succeeds, image content is decoded (`firewing/inference/multimodal.py`)
  and passed through the processor alongside the rendered chat
  template.
- If it fails (e.g. a text-only checkpoint, or your installed
  `transformers` version doesn't ship a processor for this
  architecture yet), FIREWING logs a warning and falls back to
  text-only — images in the request are ignored rather than the whole
  request failing.

## Scope and honesty check

This is implemented against Qwen3-Omni's documented processor
conventions (`AutoProcessor` + `apply_chat_template` accepting mixed
text/image content, matching the Qwen2-VL/Qwen-Omni family pattern).
**It has not been validated against real Qwen3-Omni weights in this
repo** — there's no GPU/weights available in the environment this was
built in. Before relying on it:

1. Load a real checkpoint and confirm `loaded.supports_multimodal` is
   `True` (check `/v1/system` — or just try an image request and see
   if it's actually used vs. silently ignored with a logged warning).
2. Test with a real image and confirm the model's response actually
   reflects the image content, not just the text.

Audio and video input, and speech output — all things Qwen3-Omni
supports — are **not implemented** in this beta. Text + image in,
text out is the current scope. Extending `multimodal.py` and the
engine's `_collect_images`-equivalent path for audio/video is the
natural next step if you need it.

## Dependencies

Image decoding needs Pillow:

```bash
pip install Pillow
```

(Already implied by most `transformers` multimodal extras, but listed
explicitly here since `requirements.txt` doesn't pin it by default —
add it if you enable multimodal in production.)
