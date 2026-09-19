"""FIREWING configuration system.

Configuration is loaded, in increasing priority order, from:
  1. Built-in defaults (this file)
  2. A YAML config file (configs/firewing.yaml by default)
  3. Environment variables (prefixed FIREWING_)

This ordering means a VPS operator can ship one config file per
environment and still override individual values (like secrets) with
env vars, without editing the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    # Hugging Face repo id or local path for the base model weights.
    model_path: str = "Qwen/Qwen3-Omni-30B-A3B-Instruct"
    device: str = "auto"  # "auto" | "cpu" | "cuda" | "cuda:0" ...
    dtype: str = "auto"  # "auto" | "float16" | "bfloat16" | "float32"
    quantization: str | None = None  # None | "int8" | "int4"
    max_context_tokens: int = 32768
    trust_remote_code: bool = True  # required by some HF omni architectures
    adapter_path: str | None = None  # optional path to a trained LoRA adapter (see docs/training.md)
    context_strategy: str = "drop"  # "drop" | "summarize" — see firewing/inference/context.py


@dataclass
class ApiConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    require_api_key: bool = True
    cors_allowed_origins: list[str] = field(default_factory=list)
    rate_limit_requests_per_minute: int = 60
    max_tokens_per_request: int = 4096
    request_timeout_seconds: int = 120


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_dir: str = "/var/log/firewing"
    json_logs: bool = False


@dataclass
class Settings:
    model: ModelConfig = field(default_factory=ModelConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    data_dir: str = "/var/lib/firewing"


def _apply_env_overrides(settings: Settings) -> Settings:
    """Override dataclass fields from FIREWING_<SECTION>_<FIELD> env vars."""
    for section_name in ("model", "api", "logging"):
        section = getattr(settings, section_name)
        for f in fields(section):
            env_key = f"FIREWING_{section_name.upper()}_{f.name.upper()}"
            if env_key in os.environ:
                raw = os.environ[env_key]
                setattr(section, f.name, _coerce(raw, type(getattr(section, f.name))))
    if "FIREWING_DATA_DIR" in os.environ:
        settings.data_dir = os.environ["FIREWING_DATA_DIR"]
    return settings


def _coerce(raw: str, target_type: type) -> Any:
    if target_type is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if target_type is int:
        return int(raw)
    if target_type is list:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load Settings from defaults -> YAML file -> env vars."""
    settings = Settings()

    path = Path(config_path) if config_path else Path("configs/firewing.yaml")
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        if "model" in raw:
            settings.model = ModelConfig(**{**settings.model.__dict__, **raw["model"]})
        if "api" in raw:
            settings.api = ApiConfig(**{**settings.api.__dict__, **raw["api"]})
        if "logging" in raw:
            settings.logging = LoggingConfig(**{**settings.logging.__dict__, **raw["logging"]})
        if "data_dir" in raw:
            settings.data_dir = raw["data_dir"]

    return _apply_env_overrides(settings)
