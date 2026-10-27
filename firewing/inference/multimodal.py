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
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


class MultimodalError(ValueError):
    """Raised for malformed or unsupported content parts."""


@dataclass
class ParsedContent:
    text: str
    images: list  # list of PIL.Image.Image, kept as-is for the processor


MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB max download/decode


def _decode_image(url: str):
    try:
        from PIL import Image
    except ImportError as exc:
        raise MultimodalError(
            "Image input requires Pillow. Install with: pip install Pillow"
        ) from exc

    if url.startswith("data:"):
        try:
            _header, b64data = url.split(",", 1)
            raw = base64.b64decode(b64data)
        except (ValueError, base64.binascii.Error) as exc:
            raise MultimodalError(f"Malformed data URL: {exc}") from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise MultimodalError(f"Image payload exceeds maximum allowed size ({MAX_IMAGE_BYTES // (1024 * 1024)}MB)")
        try:
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise MultimodalError(f"Invalid image data: {exc}") from exc

    if url.startswith("http://") or url.startswith("https://"):
        import urllib.request

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FIREWING/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read(MAX_IMAGE_BYTES + 1)
                if len(raw) > MAX_IMAGE_BYTES:
                    raise MultimodalError(f"Image from URL exceeds maximum allowed size ({MAX_IMAGE_BYTES // (1024 * 1024)}MB)")
        except Exception as exc:  # noqa: BLE001
            raise MultimodalError(f"Could not fetch image URL: {exc}") from exc
        try:
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise MultimodalError(f"Invalid image format from URL: {exc}") from exc

    if url.startswith("file://"):
        parsed = urlparse(url)
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        p = Path(path)
        if not p.is_file():
            raise MultimodalError(f"Image file not found: {path}")
        try:
            return Image.open(p).convert("RGB")
        except Exception as exc:
            raise MultimodalError(f"Could not open image file: {exc}") from exc

    p = Path(url)
    if p.is_file():
        try:
            return Image.open(p).convert("RGB")
        except Exception as exc:
            raise MultimodalError(f"Could not open image file: {exc}") from exc

    raise MultimodalError(
        f"Unsupported image_url scheme (expected data:, http(s)://, or local file): {url[:40]}..."
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
