# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0-beta] — Unreleased

### Added
- Initial project scaffold: `firewing/` application layer (config,
  logging, model loader, tokenizer wrapper, conversation/persona
  management, streaming inference engine).
- FastAPI server with `/health`, `/v1/models`, `/v1/system`,
  `/v1/status`, `/v1/chat/completions` (streaming + non-streaming),
  API key auth, per-key rate limiting.
- `setup-ai` CLI: `start/stop/restart/status/logs/update/config/model/doctor/chat`.
- Interactive setup wizard.
- `install.sh` for Ubuntu 22.04/24.04, systemd unit, Dockerfile,
  docker-compose.yml, nginx template.
- Documentation set (`docs/`), model card, benchmark script.
- Test suite covering config loading and unauthenticated/authenticated
  health endpoints (no GPU/weights required).

## [Unreleased]

### Added
- Documentation website (`docs/index.html`, docsify-based) with
  sidebar nav, search, and syntax highlighting, covering every
  existing docs page. Deployed automatically to GitHub Pages via
  `.github/workflows/pages.yml` on every push to `main` that touches
  `docs/`.

### Fixed
- `install.sh` now detects an EOL Debian base image (dead
  `security.debian.org` repo — e.g. bullseye after its LTS support
  closed) and disables the dead security source before running
  `apt-get update`, instead of failing the whole install with a wall
  of 404 errors. See `docs/troubleshooting.md`.

### Added
- LoRA fine-tuning pipeline (`scripts/training/`): dataset prep with
  validation, `train_lora.py` (LoRA or full fine-tune), adapter
  evaluation script, and `docs/training.md`. Model loader now supports
  `model.adapter_path` to load a trained adapter at serving time.
- Multi-user API key management: persistent `KeyStore`
  (`firewing/api/security/key_store.py`, hashed storage) plus
  `/v1/admin/keys` (create/list/revoke) and `/v1/admin/stats`, gated
  behind a separate `FIREWING_ADMIN_KEY`.
- Admin dashboard (`webui/admin.html`): system status, request stats,
  key management UI.
- Request stats tracking (`firewing/utils/stats.py`), wired into the
  chat completions route.
- Configurable context strategy: `model.context_strategy: summarize`
  now summarizes dropped conversation history via the model itself
  instead of only ever discarding it (`firewing/inference/context.py`).
  Default remains `drop` (no extra generation cost).
