# Setup AI → FIREWING 1.0 BETA

**[📖 Full documentation](https://untitledinfo.github.io/SetupAi/)** · [GitHub](https://github.com/untitledinfo/SetupAi)

FIREWING is a self-hosted AI assistant platform: an API server, CLI,
web UI, and installer built around the **Qwen3-Omni** base model.

> **FIREWING is not an independently trained model.** It is built on
> `Qwen/Qwen3-Omni-30B-A3B-Instruct` (Apache License 2.0). See
> [`NOTICE`](./NOTICE) for full attribution and
> [`docs/model-card.md`](./docs/model-card.md) for details. Everything
> outside the base model weights/tokenizer — the inference engine,
> API, CLI, installer, and web UI — is original code developed for
> this project.

## What's here

```
firewing/     the application layer (model loading, inference, API)
setup_ai/     the CLI and installer
webui/        the web chat interface (placeholder — see webui/README.md)
configs/      example configuration
docs/         installation, API, CLI, security, and model docs
scripts/      deployment templates and benchmark script
tests/        automated tests
```

## Quickstart (local, no install)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp configs/firewing.example.yaml configs/firewing.yaml
cp .env.example .env   # then set FIREWING_API_KEYS

# CLI chat
python -m setup_ai.cli.main chat

# or run the API
uvicorn firewing.api.server:app --reload
curl http://localhost:8000/health
```

## Production install (Ubuntu 22.04/24.04 VPS)

```bash
git clone <repository>   # replace with your actual repo URL
cd setup-ai
sudo bash install.sh
```

There is intentionally no `curl | bash` one-liner yet — that requires
a real hosted URL for `install.sh`, which doesn't exist until this
repository has a public home. See [`docs/installation.md`](./docs/installation.md).

## Docker

```bash
cp .env.example .env   # set FIREWING_API_KEYS
docker compose up -d
```

## License

FIREWING's own code (everything except the base model) is licensed
under [Apache License 2.0](./LICENSE). The base model weights and
tokenizer are Qwen3-Omni, also Apache 2.0 — see [`NOTICE`](./NOTICE).

## Fine-tuning

Want to train the base model further instead of just serving it
stock? See [`docs/training.md`](./docs/training.md) — LoRA fine-tuning
pipeline with data validation, training, and before/after evaluation.
Needs your own GPU hardware (48GB+ VRAM realistic minimum); this repo
provides the scripts, not the compute or the training data.

## Admin

Multi-user API keys and request stats are managed separately from the
chat API, behind their own `FIREWING_ADMIN_KEY` — see
[`docs/api.md`](./docs/api.md) (Admin API section) and
[`webui/admin.html`](./webui/admin.html) for a small dashboard.

## Status

**Beta.** See [`docs/troubleshooting.md`](./docs/troubleshooting.md)
for known limitations (in-memory rate limiting and stats tracking,
quantization support depends on your platform).
