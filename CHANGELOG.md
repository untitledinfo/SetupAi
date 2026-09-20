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

### Fixed
- `firewing/model/loader.py`: fixed `ValueError: Unrecognized
  configuration class ... for this kind of AutoModel` when loading the
  default Qwen3-Omni checkpoint. The loader now resolves the correct
  `transformers` model class from `config.architectures` instead of
  hard-coding `AutoModelForCausalLM`, with a fallback chain (exact
  architecture class → generic multimodal Auto classes →
  `AutoModelForCausalLM`) so both omni/multimodal and plain text
  checkpoints load correctly. Also: `dtype=` is tried before the
  deprecated `torch_dtype=` kwarg, and big/MoE checkpoints now load with
  `device_map="auto"` instead of a manual `.to(device)`.
- `requirements.txt`: bumped `transformers>=4.57.0` (first PyPI release
  with Qwen3-Omni support) and added `qwen-omni-utils`, `soundfile`,
  and `huggingface_hub` as explicit dependencies.
- `install.sh`: installs `ffmpeg` (required by `qwen-omni-utils` for
  audio/video input) alongside the existing system packages.

### Added
- `setup-ai model list` / `setup-ai model search <keyword>` (and
  menu.sh → option 1 → 5/6): browse or search public models on the
  Hugging Face Hub and print their exact repo id, downloads, likes, and
  gated status — no API key needed, since Hub listing/search is
  anonymous for public repos. Feeds directly into
  `setup-ai model set --path <id>`.
- `setup-ai chat` now prints a best-effort hardware pre-flight warning
  (VRAM/RAM vs. the configured model + quantization) before attempting
  to load, instead of only discovering an OOM/slow-CPU situation
  minutes into a first-run weight download.


- **Multimodal (image) input**: OpenAI-vision-style content parts in
  chat messages, processor auto-loading with text-only fallback. See
  `docs/multimodal.md`. Not yet validated against real weights (no
  GPU in the build environment).
- **Function/tool calling**: OpenAI-compatible `tools`/`tool_calls`
  API surface, parsing Qwen's native Hermes-style `<tool_call>` tags.
  Server-side `ToolRegistry` with example tools, wired into
  `setup-ai chat`. `tools` + `stream: true` is rejected (400) —
  tool-call parsing needs the complete response. See
  `docs/tool-calling.md`.
- **Persistent conversations**: SQLite-backed server-side conversation
  storage and a new `/v1/conversations` API (create/list/get/delete,
  plus `POST .../messages` to continue a conversation without
  resending full history). See `docs/conversations.md`.
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
- `ConversationStore` was touching disk at construction time (before
  any actual save) — fixed to defer directory/schema creation until
  first real use, matching `KeyStore`'s lazy pattern, so app startup
  doesn't require write access to `data_dir` unless something is
  actually persisted.
- Chat completions route was checking model-loaded status before
  validating message shape (e.g. a `role: "tool"` message missing
  `tool_call_id` would return 503 instead of 400). Reordered so
  request validation happens first.
