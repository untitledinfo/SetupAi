"""Logging setup for FIREWING.

Two rules that matter more than the rest:
  1. Never log secrets (API keys, tokens). Use `redact()` on anything
     that might contain one before it reaches a log line.
  2. Every API request gets a request_id that shows up in every log
     line related to it, so operators can grep one request end to end.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_REDACT_PLACEHOLDER = "***REDACTED***"


def redact(value: str | None, keep_last: int = 4) -> str:
    """Return a safe-to-log version of a secret-shaped string."""
    if not value:
        return ""
    if len(value) <= keep_last:
        return _REDACT_PLACEHOLDER
    return f"{_REDACT_PLACEHOLDER}{value[-keep_last:]}"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO", log_dir: str | None = None, json_logs: bool = False) -> None:
    root = logging.getLogger("firewing")
    root.setLevel(level.upper())
    root.handlers.clear()

    formatter: logging.Formatter
    if json_logs:
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(Path(log_dir) / "firewing.log")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            # Non-fatal: fall back to stdout-only logging (e.g. read-only
            # filesystem, permissions issue on a locked-down VPS).
            root.warning("Could not open log_dir=%s, logging to stdout only", log_dir)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"firewing.{name}")
