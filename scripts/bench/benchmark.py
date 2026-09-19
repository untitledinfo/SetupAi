"""Benchmark FIREWING inference on this machine.

Measures, against the *actually loaded* model on *this* hardware:
  - time to first token
  - total response latency
  - tokens/sec (generation phase)
  - peak RAM/VRAM usage

Usage:
    python scripts/bench/benchmark.py --prompt "Explain photosynthesis" --max-tokens 256

Results are printed and NOT hardcoded anywhere else in the codebase —
docs/model-card.md explicitly says to fill in real numbers from this
script's output, on real target hardware, rather than estimating.
"""

from __future__ import annotations

import argparse
import time

from firewing.config.settings import load_settings
from firewing.model.loader import load_model
from firewing.inference.engine import InferenceEngine, GenerationParams
from firewing.inference.conversation import Conversation


def _peak_ram_mb() -> float:
    import resource

    # ru_maxrss is KB on Linux, bytes on macOS — normalize to MB for Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _vram_mb() -> float | None:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / (1024 * 1024)
    except ImportError:
        pass
    return None


def run_benchmark(prompt: str, max_tokens: int, config_path: str | None) -> None:
    settings = load_settings(config_path)
    loaded = load_model(settings.model)
    engine = InferenceEngine(loaded, settings.model.max_context_tokens)

    conversation = Conversation(system_prompt="You are a helpful assistant.")
    conversation.add_user(prompt)
    params = GenerationParams(max_tokens=max_tokens)

    start = time.perf_counter()
    first_token_time = None
    token_count = 0

    for chunk in engine.stream(conversation, params):
        if first_token_time is None:
            first_token_time = time.perf_counter()
        token_count += len(engine.tokenizer.encode(chunk))

    end = time.perf_counter()

    total_latency = end - start
    ttft = (first_token_time - start) if first_token_time else None
    generation_time = (end - first_token_time) if first_token_time else total_latency
    tokens_per_sec = token_count / generation_time if generation_time > 0 else 0.0

    print("=== FIREWING Benchmark ===")
    print(f"device:              {loaded.device}")
    print(f"dtype:               {loaded.dtype}")
    print(f"quantization:        {loaded.quantization}")
    print(f"prompt tokens:       {engine.tokenizer.count_tokens(prompt)}")
    print(f"generated tokens:    {token_count}")
    print(f"time to first token: {ttft:.3f}s" if ttft is not None else "time to first token: n/a")
    print(f"total latency:       {total_latency:.3f}s")
    print(f"tokens/sec:          {tokens_per_sec:.2f}")
    print(f"peak RAM:            {_peak_ram_mb():.1f} MB")
    vram = _vram_mb()
    print(f"peak VRAM:           {vram:.1f} MB" if vram is not None else "peak VRAM:           n/a (no CUDA)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark FIREWING inference")
    parser.add_argument("--prompt", default="Explain how photosynthesis works in three sentences.")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    run_benchmark(args.prompt, args.max_tokens, args.config)


if __name__ == "__main__":
    main()
