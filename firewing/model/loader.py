"""FIREWING model loader.

This is original code: it decides *how* to load the upstream Qwen3-Omni
weights (device, dtype, quantization) based on the running hardware and
the operator's config. It does not reimplement the model architecture
itself — that comes from the `transformers` library / the upstream
Qwen3-Omni repo, per the Apache-2.0 terms documented in /NOTICE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from firewing.config.settings import ModelConfig
from firewing.utils.logging import get_logger

logger = get_logger("model.loader")


class ModelLoadError(RuntimeError):
    """Raised when the base model cannot be loaded."""


@dataclass
class LoadedModel:
    model: Any
    tokenizer: Any
    device: str
    dtype: str
    quantization: str | None


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _resolve_dtype(requested: str, device: str) -> str:
    if requested != "auto":
        return requested
    return "bfloat16" if device.startswith("cuda") else "float32"


def load_model(config: ModelConfig) -> LoadedModel:
    """Load the base model + tokenizer according to `config`.

    Raises ModelLoadError with a clear, actionable message on failure
    rather than letting an opaque exception from `transformers` bubble
    all the way up to the CLI/API caller.
    """
    device = _resolve_device(config.device)
    dtype = _resolve_dtype(config.dtype, device)

    logger.info(
        "Loading model_path=%s device=%s dtype=%s quantization=%s",
        config.model_path,
        device,
        dtype,
        config.quantization,
    )

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise ModelLoadError(
            "Missing required dependencies (torch, transformers). "
            "Install with: pip install -r requirements.txt"
        ) from exc

    torch_dtype = getattr(torch, dtype, None)
    if torch_dtype is None:
        raise ModelLoadError(f"Unrecognized dtype '{dtype}'")

    quant_kwargs: dict[str, Any] = {}
    if config.quantization == "int8":
        quant_kwargs["load_in_8bit"] = True
    elif config.quantization == "int4":
        quant_kwargs["load_in_4bit"] = True
    elif config.quantization is not None:
        raise ModelLoadError(
            f"Unsupported quantization '{config.quantization}'. Use null, 'int8', or 'int4'."
        )

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            config.model_path, trust_remote_code=config.trust_remote_code
        )
        model = AutoModelForCausalLM.from_pretrained(
            config.model_path,
            torch_dtype=torch_dtype,
            trust_remote_code=config.trust_remote_code,
            **quant_kwargs,
        )
        if device != "cpu" and not quant_kwargs:
            model = model.to(device)
        model.eval()
    except OSError as exc:
        raise ModelLoadError(
            f"Could not load model '{config.model_path}'. Check that the path/repo "
            "id is correct and, for a local path, that the weights have been "
            "downloaded. Original error: " + str(exc)
        ) from exc

    if config.adapter_path:
        try:
            from peft import PeftModel

            logger.info("Loading LoRA adapter from %s", config.adapter_path)
            model = PeftModel.from_pretrained(model, config.adapter_path)
        except ImportError as exc:
            raise ModelLoadError(
                "adapter_path is set but 'peft' is not installed. "
                "Install with: pip install -r requirements-training.txt"
            ) from exc
        except (OSError, ValueError) as exc:
            raise ModelLoadError(
                f"Could not load adapter from '{config.adapter_path}': {exc}"
            ) from exc

    return LoadedModel(
        model=model,
        tokenizer=tokenizer,
        device=device,
        dtype=dtype,
        quantization=config.quantization,
    )
