# FIREWING 1.0 BETA

Welcome to the docs for **Setup AI / FIREWING** — a self-hosted AI
assistant platform (API server, CLI, web UI, installer) built on top
of the **Qwen3-Omni** base model.

> **FIREWING is not an independently trained model.** It's built on
> `Qwen/Qwen3-Omni-30B-A3B-Instruct` (Apache License 2.0). See the
> [NOTICE](https://github.com/untitledinfo/SetupAi/blob/main/NOTICE)
> file for full attribution and [Model Card](model-card.md) for
> details.

## Where to start

- New here? → [Quickstart](quickstart.md)
- Setting up a VPS? → [Installation](installation.md) then [VPS Sizing](vps.md)
- Running in Docker? → [Docker](docker.md)
- Have a GPU? → [GPU Setup](gpu.md) · CPU-only? → [CPU-Only](cpu.md)
- Building against the API? → [API Reference](api.md)
- Want to fine-tune the model? → [Fine-Tuning](training.md)
- Something broken? → [Troubleshooting](troubleshooting.md)

## What's in this project

```
firewing/     application layer — config, model loading, inference, API
setup_ai/     CLI and installer
webui/        chat interface + admin dashboard
scripts/      deployment templates, benchmarks, training pipeline
docs/         this site
```

## License

FIREWING's own code is [Apache 2.0](https://github.com/untitledinfo/SetupAi/blob/main/LICENSE).
The base model weights are Qwen3-Omni, also Apache 2.0 — see
[NOTICE](https://github.com/untitledinfo/SetupAi/blob/main/NOTICE).
