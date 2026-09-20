"""Multimodal (image) input handling.

Scope for this beta: image understanding only (text + image in, text
out). Qwen3-Omni also supports audio/video in and speech out — those
are tracked as future work (see docs/multimodal.md) rather than
half-implemented here.

Content parts follow the same shape OpenAI's vision API uses, so
existing client code/examples are easy to adapt:

    {"type": "text", "text": "What's in this image?"}
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass


class MultimodalError(ValueError):
    """Raised for malformed or unsupported content parts."""


@dataclass
class ParsedContent:
    text: str
    images: list  # list of PIL.Image.Image, kept as-is for the processor


def _decode_image(url: str):
    try:
        from PIL import Image
    except ImportError as exc:
        raise MultimodalError(
            "Image input requires Pillow. Install with: pip install Pillow"
        ) from exc

    if url.startswith("data:"):
        try:
            header, b64data = url.split(",", 1)
            raw = base64.b64decode(b64data)
        except (ValueError, base64.binascii.Error) as exc:
            raise MultimodalError(f"Malformed data URL: {exc}") from exc
        return Image.open(io.BytesIO(raw)).convert("RGB")

    if url.startswith("http://") or url.startswith("https://"):
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                raw = resp.read()
        except Exception as exc:  # noqa: BLE001 — network errors vary by platform
            raise MultimodalError(f"Could not fetch image URL: {exc}") from exc
        return Image.open(io.BytesIO(raw)).convert("RGB")

    raise MultimodalError(
        f"Unsupported image_url scheme (expected data: or http(s)://): {url[:40]}..."
    )


def parse_content(content) -> ParsedContent:
    """Normalize a ChatMessage's `content` (plain string OR a list of
    OpenAI-style content parts) into text + a list of decoded images.
    """
    if isinstance(content, str):
        return ParsedContent(text=content, images=[])

    text_parts: list[str] = []
    images = []
    for part in content:
        part_type = part.get("type")
        if part_type == "text":
            text_parts.append(part.get("text", ""))
        elif part_type == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if not url:
                raise MultimodalError("image_url content part missing 'url'")
            images.append(_decode_image(url))
        else:
            raise MultimodalError(f"Unsupported content part type: {part_type!r}")

    return ParsedContent(text="\n".join(text_parts), images=images)
