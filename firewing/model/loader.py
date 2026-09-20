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
    processor: Any = None  # AutoProcessor, only set if multimodal loading succeeds

    @property
    def supports_multimodal(self) -> bool:
        return self.processor is not None


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


def _candidate_model_classes(model_path: str, trust_remote_code: bool) -> tuple[list[tuple[Any, str]], Any]:
    """Work out which `transformers` model class can actually load this
    checkpoint, instead of hard-coding AutoModelForCausalLM.

    Bug this fixes: checkpoints like Qwen3-Omni ship a
    `Qwen3OmniMoeConfig`, which AutoModelForCausalLM does not know how to
    map to a model class ("Unrecognized configuration class ... for this
    kind of AutoModel"). The config itself always names the correct
    class(es) in `config.architectures` (e.g. "Qwen3OmniMoeForConditionalGeneration"),
    so we read that first and only fall back to the generic Auto classes
    for plain text checkpoints where architectures is empty/unhelpful.

    Returns an ordered list of (class, human-readable name) to try, most
    specific first.
    """
    import transformers
    from transformers import AutoConfig

    candidates: list[tuple[Any, str]] = []

    try:
        config = AutoConfig.from_pretrained(model_path, trust_remote_code=trust_remote_code)
    except Exception as exc:  # noqa: BLE001 — surfaced properly by the caller's own try/except
        raise ModelLoadError(
            f"Could not read config.json for '{model_path}': {exc}. Check the repo id/path, "
            "and that you're online (or the config is already cached) if this is a HF repo."
        ) from exc

    architectures = list(getattr(config, "architectures", None) or [])
    for arch_name in architectures:
        cls = getattr(transformers, arch_name, None)
        if cls is not None:
            candidates.append((cls, arch_name))

    # Generic multimodal fallback (covers most vision/audio/omni "Auto"-style
    # checkpoints even when the exact class above isn't importable, e.g. an
    # installed transformers version that is one release behind).
    for auto_name in ("AutoModelForImageTextToText", "AutoModelForVision2Seq"):
        auto_cls = getattr(transformers, auto_name, None)
        if auto_cls is not None:
            candidates.append((auto_cls, auto_name))

    # Plain text causal-LM fallback — this is what almost every non-multimodal
    # checkpoint (Qwen, Llama, Mistral, etc.) actually needs, and it's also a
    # harmless last resort to attempt for anything else.
    from transformers import AutoModelForCausalLM

    # De-duplicate while preserving order (an architecture name can also be
    # one of the Auto class names in edge cases).
    seen: set[str] = set()
    deduped: list[tuple[Any, str]] = []
    for cls, name in candidates:
        if name not in seen:
            seen.add(name)
            deduped.append((cls, name))
    deduped.append((AutoModelForCausalLM, "AutoModelForCausalLM"))

    return deduped, config


def _try_load_processor(model_path: str, trust_remote_code: bool) -> Any:
    """Best-effort load of an AutoProcessor for multimodal (image/audio)
    input handling. Qwen3-Omni ships a processor for this; if it's
    unavailable (e.g. a text-only checkpoint, or the installed
    `transformers` version doesn't support this architecture's
    processor yet), FIREWING degrades to text-only rather than failing
    the whole model load over it.
    """
    try:
        from transformers import AutoProcessor

        return AutoProcessor.from_pretrained(model_path, trust_remote_code=trust_remote_code)
    except Exception as exc:  # noqa: BLE001 — deliberately broad, this is a soft-fail path
        logger.warning(
            "Could not load multimodal processor for %s (%s). "
            "Falling back to text-only mode.",
            model_path,
            exc,
        )
        return None


def load_model(config: ModelConfig) -> LoadedModel:
    """Load the base model + tokenizer (+ processor, if available)
    according to `config`.

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
        from transformers import AutoTokenizer
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

    # Work out *which* model class this checkpoint actually needs (fixes:
    # "Unrecognized configuration class ... for this kind of AutoModel" when
    # config.model_path is a multimodal/omni checkpoint like Qwen3-Omni,
    # which AutoModelForCausalLM cannot load).
    candidates, hf_config = _candidate_model_classes(config.model_path, config.trust_remote_code)

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            config.model_path, trust_remote_code=config.trust_remote_code
        )
    except OSError as exc:
        raise ModelLoadError(
            f"Could not load tokenizer for '{config.model_path}'. Check that the path/repo "
            "id is correct and, for a local path, that the weights have been "
            "downloaded. Original error: " + str(exc)
        ) from exc

    # Big (especially MoE) checkpoints load far more reliably with
    # device_map="auto" (lets `accelerate` place/shard layers across
    # whatever GPU(s)/CPU RAM are actually available) than a manual
    # `.to(device)` call after the fact, which can OOM or silently leave
    # part of the model on the wrong device for MoE architectures.
    use_device_map = device != "cpu" or quant_kwargs
    load_kwargs: dict[str, Any] = {
        "trust_remote_code": config.trust_remote_code,
        **quant_kwargs,
    }
    if use_device_map:
        load_kwargs["device_map"] = "auto"

    last_error: Exception | None = None
    model = None
    tried: list[str] = []
    for model_cls, class_name in candidates:
        tried.append(class_name)
        try:
            try:
                # transformers >= 4.56 renamed `torch_dtype` -> `dtype`.
                model = model_cls.from_pretrained(
                    config.model_path, dtype=torch_dtype, **load_kwargs
                )
            except TypeError:
                model = model_cls.from_pretrained(
                    config.model_path, torch_dtype=torch_dtype, **load_kwargs
                )
            logger.info("Loaded %s using %s", config.model_path, class_name)
            break
        except ValueError as exc:
            # "Unrecognized configuration class" / wrong-AutoModel-for-this-
            # config errors land here — try the next candidate class instead
            # of failing outright.
            last_error = exc
            continue
        except OSError as exc:
            raise ModelLoadError(
                f"Could not load model '{config.model_path}'. Check that the path/repo "
                "id is correct and, for a local path, that the weights have been "
                "downloaded. Original error: " + str(exc)
            ) from exc

    if model is None:
        arch_hint = ", ".join(getattr(hf_config, "architectures", None) or []) or "unknown"
        raise ModelLoadError(
            f"Could not load '{config.model_path}' with any of: {', '.join(tried)}. "
            f"Checkpoint architecture(s): {arch_hint}. This usually means your installed "
            "'transformers' is too old for this checkpoint — try: pip install -U "
            "'transformers>=4.57' (Qwen3-Omni support landed in transformers 4.57.0). "
            f"Original error: {last_error}"
        )

    if not use_device_map:
        model = model.to(device)
    model.eval()

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

    processor = None
    if config.enable_multimodal:
        processor = _try_load_processor(config.model_path, config.trust_remote_code)

    return LoadedModel(
        model=model,
        tokenizer=tokenizer,
        device=device,
        dtype=dtype,
        quantization=config.quantization,
        processor=processor,
    )
