# GPU Setup

## Requirements

- NVIDIA GPU, ≥24GB VRAM recommended for quantized inference of the
  30B/3B-active MoE base model, 48GB+ for higher-precision/production use
- NVIDIA driver + CUDA 12.x
- For Docker: `nvidia-container-toolkit`

## Verifying your setup

```bash
nvidia-smi
setup-ai doctor
```

`doctor` reports GPU name, total/free VRAM, and detected CUDA version
using the same detection code the API's `/v1/system` endpoint uses.

## Quantization

Set in `configs/firewing.yaml`:

```yaml
model:
  quantization: int8   # or int4 for smaller VRAM footprint, or null for full precision
```

`int8`/`int4` require the `bitsandbytes` package (in `requirements.txt`,
platform-guarded to Linux). If it's not installed or doesn't build on
your platform, set `quantization: null` and run full precision (if
VRAM/RAM allows) or fall back to CPU.

## No GPU?

FIREWING will run CPU-only (`model.device: cpu` or leave `auto`, which
falls back to CPU when no CUDA device is found) — expect meaningfully
higher latency. Use `scripts/bench/benchmark.py` to measure actual
numbers on your hardware rather than assuming.
