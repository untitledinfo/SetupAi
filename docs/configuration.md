# Configuration

FIREWING loads settings in this order (later overrides earlier):

1. Built-in defaults (`firewing/config/settings.py`)
2. `configs/firewing.yaml` (copy from `configs/firewing.example.yaml`)
3. Environment variables: `FIREWING_<SECTION>_<FIELD>`

## Full reference

| Key | Env var | Default | Notes |
|---|---|---|---|
| `model.model_path` | `FIREWING_MODEL_MODEL_PATH` | `Qwen/Qwen3-Omni-30B-A3B-Instruct` | HF repo id or local path |
| `model.device` | `FIREWING_MODEL_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, `cuda:0` |
| `model.dtype` | `FIREWING_MODEL_DTYPE` | `auto` | `auto`, `float16`, `bfloat16`, `float32` |
| `model.quantization` | `FIREWING_MODEL_QUANTIZATION` | `null` | `null`, `int8`, `int4` |
| `model.max_context_tokens` | `FIREWING_MODEL_MAX_CONTEXT_TOKENS` | `32768` | |
| `model.adapter_path` | `FIREWING_MODEL_ADAPTER_PATH` | `null` | Path to a trained LoRA adapter — see `docs/training.md` |
| `model.context_strategy` | `FIREWING_MODEL_CONTEXT_STRATEGY` | `drop` | `drop` or `summarize` — see `firewing/inference/context.py` |
| `model.enable_multimodal` | `FIREWING_MODEL_ENABLE_MULTIMODAL` | `true` | Attempt to load an image processor at startup |
| `model.enable_tool_calling` | `FIREWING_MODEL_ENABLE_TOOL_CALLING` | `true` | Used by `setup-ai chat`'s built-in tool demo; the API always accepts `tools` regardless of this flag |
| `api.port` | `FIREWING_API_PORT` | `8000` | |
| `api.require_api_key` | `FIREWING_API_REQUIRE_API_KEY` | `true` | Keys themselves come from `FIREWING_API_KEYS`, not this file |
| `api.rate_limit_requests_per_minute` | `FIREWING_API_RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Per API key |
| `api.max_tokens_per_request` | `FIREWING_API_MAX_TOKENS_PER_REQUEST` | `4096` | |
| `logging.level` | `FIREWING_LOGGING_LEVEL` | `INFO` | |
| `logging.json_logs` | `FIREWING_LOGGING_JSON_LOGS` | `false` | |

## Secrets

API keys are **never** read from `configs/firewing.yaml`. Set them via
the `FIREWING_API_KEYS` environment variable (comma-separated), loaded
from `.env` in local/Docker use or `EnvironmentFile=` in the systemd
unit. Never commit a real `.env` file.

`FIREWING_ADMIN_KEY` is a separate, higher-privilege key for
`/v1/admin/*` (key management, request stats) — see `docs/api.md`.
Leaving it unset disables the admin API entirely rather than falling
back to any other key.
