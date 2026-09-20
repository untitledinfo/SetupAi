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

## Features

- OpenAI-compatible `/v1/chat/completions` (streaming + non-streaming)
- **Multimodal input** — image understanding via content parts, see [`docs/multimodal.md`](./docs/multimodal.md)
- **Function/tool calling** — OpenAI-compatible, see [`docs/tool-calling.md`](./docs/tool-calling.md)
- **Persistent conversations** — server-held chat history, see [`docs/conversations.md`](./docs/conversations.md)
- Multi-user API keys + admin dashboard, request stats
- LoRA fine-tuning pipeline for the base model
- CLI, web chat UI, Docker, systemd, one-command install

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
git clone https://github.com/untitledinfo/SetupAi.git
cd SetupAi/setup-ai
sudo bash install.sh
```

There is intentionally no `curl | bash` one-liner — `install.sh` needs
root and modifies system state (users, systemd, firewall), so it's
meant to be reviewed from a clone rather than piped blind from a URL.

### Or drive everything from one menu

```bash
git clone https://github.com/untitledinfo/SetupAi.git
cd SetupAi/setup-ai
sudo bash menu.sh
```

```
0) Install Setup AI
1) Models Install
2) Uninstall
3) Domain Link (Cloudflare / IP / DNS)
4) Chat Locally
5) SSL / HTTPS Install
6) API
7) Database
8) Chat with Terminal AI (hi -> thinking -> reply, fully working test)
9) Exit
```

`menu.sh` shells out to `install.sh`, `uninstall.sh`, the `setup-ai`
CLI, `nginx`, `certbot`, and the Cloudflare API — each option is a
thin wrapper around a real command, documented in
[`docs/cli.md`](./docs/cli.md#interactive-menu-menush). See
[`docs/installation.md`](./docs/installation.md) for details.

## Docker

```bash
cp .env.example .env   # set FIREWING_API_KEYS
docker compose up -d
```

## License

FIREWING's own code (everything except the base model) is licensed
under [Apache License 2.0](./LICENSE). The base model weights and
tokenizer are Qwen3-Omni, also Apache 2.0 — see [`NOTICE`](./NOTICE).

## Fine-tuning — making the served model actually yours

FIREWING serves the stock upstream weights unless you change that.
"Fully owning" the model in a way that's honest means fine-tuning a
LoRA adapter — not relabeling the base weights as independently
trained. See [`docs/training.md`](./docs/training.md) for the
pipeline (data validation, training, before/after evaluation). Needs
your own GPU hardware (48GB+ VRAM realistic minimum); this repo
provides the scripts, not the compute or the training data.

Once you have an adapter, point FIREWING at it:

```bash
setup-ai model set --adapter /path/to/your/adapter
# or, to also switch the base checkpoint/upgrade at the same time:
setup-ai model upgrade --path <hf-repo-or-local-path> --adapter /path/to/your/adapter
sudo systemctl restart firewing
```

## Admin

Multi-user API keys and request stats are managed separately from the
chat API, behind their own `FIREWING_ADMIN_KEY` — see
[`docs/api.md`](./docs/api.md) (Admin API section) and
[`webui/admin.html`](./webui/admin.html) for a small dashboard.

## Status

**Beta.** See [`docs/troubleshooting.md`](./docs/troubleshooting.md)
for known limitations (in-memory rate limiting and stats tracking,
quantization support depends on your platform).
