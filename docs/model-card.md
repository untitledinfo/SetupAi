# FIREWING 1.0 BETA — Model Card

## Model description

FIREWING 1.0 BETA is a self-hosted AI assistant *platform*: an
inference engine, HTTP API, CLI, and web interface wrapped around a
base language model. It is **not** a new model architecture and the
weights are **not** independently trained.

## Architecture

- Base model: `Qwen/Qwen3-Omni-30B-A3B-Instruct` — a mixture-of-experts
  (MoE) transformer, 30B total parameters / 3B active per token,
  natively multimodal (text, image, audio, video in; text and speech
  out).
- FIREWING's application layer (loading, inference streaming,
  conversation management, API, CLI) is original code — see
  [`NOTICE`](../NOTICE) for the exact attribution boundary.

## Base model / upstream

| | |
|---|---|
| Upstream project | Qwen3-Omni |
| Upstream org | Qwen Team, Alibaba Group |
| Upstream repo | https://github.com/QwenLM/Qwen3-Omni |
| Checkpoint used | `Qwen/Qwen3-Omni-30B-A3B-Instruct` |
| Upstream license | Apache License 2.0 |

## License

FIREWING's own code: Apache License 2.0 (see [`LICENSE`](../LICENSE)).
Base model: Apache License 2.0 (upstream, unmodified terms).

## Training / fine-tuning information

*Placeholder — fill in honestly before release.* As of this beta,
FIREWING ships the stock Qwen3-Omni-30B-A3B-Instruct weights with no
additional fine-tuning. If/when FIREWING fine-tunes the base model,
this section must describe: dataset sources, size, and licensing;
training method (full fine-tune, LoRA, etc.); and evaluation results
from *actual runs*, not estimates.

## Intended use

- Self-hosted chat assistant for individuals/small teams running their
  own VPS or GPU server.
- Developer integration via the OpenAI-compatible `/v1/chat/completions`
  API.

## Out-of-scope use

- High-stakes decisions (medical, legal, financial) without human
  review.
- Any use that violates the Qwen3-Omni upstream license or Alibaba's
  acceptable use terms — review those directly before commercial
  deployment at scale.

## Limitations

- Beta software: rate limiting is in-memory and per-process (does not
  share state across multiple replicas — see `docs/troubleshooting.md`).
- No context summarization yet; long conversations are truncated by
  dropping the oldest turns.
- Multimodal (audio/video) input handling in the API layer is not yet
  implemented in this beta — text-in/text-out only. Tracked for a
  future release.

## Known beta issues

*Placeholder — update as issues are found during real testing.*

## Safety considerations

FIREWING inherits whatever safety behavior is present in the base
Qwen3-Omni-Instruct model. FIREWING's application layer adds: API key
authentication, per-key rate limiting, and structured error handling
that avoids leaking secrets or stack traces to clients. It does not
add its own content-safety layer in this beta.

## Evaluation

*No FIREWING-specific benchmark numbers exist yet.* Do not publish
performance claims until the benchmark script in `scripts/bench/`
has actually been run against target hardware. Record real results
here once available, with the exact hardware and config used.

## Hardware requirements

See [`docs/vps.md`](./vps.md) and [`docs/gpu.md`](./gpu.md) for
current tiering guidance (CPU-only / single-GPU / production).

## Quantization support

int8 and int4 loading paths are implemented via `bitsandbytes` (see
`firewing/model/loader.py`), toggled by `model.quantization` in
config. Actual quality/speed tradeoffs are hardware-dependent and not
yet benchmarked — see Evaluation above.

## Version history

| Version | Notes |
|---|---|
| 1.0.0-beta | Initial public scaffold: CLI, API, Docker, systemd, install script. |

## Attribution

See [`NOTICE`](../NOTICE) for the full, required attribution to the
Qwen3-Omni project.
