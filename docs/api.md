# API Reference

Base URL: `http://<host>:8000` (put behind nginx + TLS for production —
see `docs/vps.md`).

Auth: `Authorization: Bearer <api_key>` on every endpoint marked
"authenticated" below. Keys are configured via `FIREWING_API_KEYS` env var
or managed through the KeyStore via Admin API/CLI.

## `GET /health`
Unauthenticated. Liveness check for Docker/systemd/nginx.

```json
{"status": "ok", "version": "1.0.0-beta", "model_loaded": true}
```

## `GET /ready`
Unauthenticated. Readiness probe: returns HTTP 200 OK only when the model inference engine is loaded and ready to serve requests (returns HTTP 503 if loading or failed).

```json
{"status": "ready", "model": "Qwen/Qwen3-Omni-30B-A3B-Instruct", "version": "1.0.0-beta"}
```

## `GET /v1/models`
Unauthenticated. Lists available models with metadata and context length.

## `GET /v1/personas`
Unauthenticated. Lists available personas (e.g. `default`, `coding`, `concise`, `creative`) and their system prompts.

## `GET /v1/personas/{name}`
Unauthenticated. Fetches a specific persona preset.

## `GET /v1/system` (authenticated)
Hardware/runtime info: OS, CPU, RAM (cross-platform), GPU, VRAM, CUDA version, Docker availability.

## `GET /v1/status` (authenticated)
Basic status: model name, version, running state, multimodal support.

## `POST /v1/chat/completions` (authenticated)

Request:
```json
{
  "model": "firewing-1.0-beta",
  "messages": [{"role": "user", "content": "Hello"}],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 1024,
  "stream": false,
  "persona": "default",
  "tools": null,
  "tool_choice": null
}
```

`messages[].content` accepts either a plain string or a list of
OpenAI-vision-style content parts (`{"type": "text", ...}` /
`{"type": "image_url", "image_url": {"url": "..."}}`) — see
[Multimodal Input](multimodal.md). `tools` follows the OpenAI function
schema — see [Function / Tool Calling](tool-calling.md).

Non-streaming response:
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "firewing-1.0-beta",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}
  ]
}
```

Streaming (`"stream": true`): Standard OpenAI Server-Sent Events with `chat.completion.chunk` JSON payloads, terminated by `data: [DONE]`.

## `POST /v1/embeddings` (authenticated)

Generate vector embeddings compatible with OpenAI embedding clients.

Request:
```json
{
  "input": "Text to embed",
  "model": "firewing-1.0-beta"
}
```

Response:
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.012, -0.045, ...]
    }
  ],
  "model": "firewing-1.0-beta",
  "usage": {"prompt_tokens": 4, "total_tokens": 4}
}
```

## Persistent conversations (authenticated)

See [Persistent Conversations](conversations.md) for the full
`/v1/conversations` API:
- `POST /v1/conversations`: Create conversation (supports `persona` and `system_prompt`)
- `GET /v1/conversations`: List conversations
- `GET /v1/conversations/{id}`: Fetch conversation details and messages
- `PATCH /v1/conversations/{id}`: Update title or persona
- `POST /v1/conversations/{id}/messages`: Add message and generate response (supports `stream: true`)
- `POST /v1/conversations/{id}/clear`: Clear message history
- `GET /v1/conversations/{id}/export?format=markdown|json`: Export conversation
- `DELETE /v1/conversations/{id}`: Delete conversation

## Admin API (requires `FIREWING_ADMIN_KEY`, not a regular API key)

### `POST /v1/admin/keys`
Create a new API key. Request: `{"label": "mobile app"}`. Response
includes the plaintext key **exactly once** — it's only ever stored
hashed after this.

### `GET /v1/admin/keys`
List keys (label, id, created_at, revoked, last_used_at, request_count).

### `PATCH /v1/admin/keys/{key_id}`
Update key label. Request: `{"label": "new-label"}`.

### `DELETE /v1/admin/keys/{key_id}`
Revoke a key (or permanently delete with `?permanent=true`).

### `GET /v1/admin/stats`
Aggregate request stats: uptime, total requests, error rate, tokens generated, avg latency, plus p50/p90/p95 latency percentiles.

A dashboard for these is in `webui/admin.html`.

## Errors

All errors return:
```json
{"error": {"type": "...", "message": "...", "request_id": "req_..."}}
```

`401` invalid/missing API key · `429` rate limit exceeded (includes `Retry-After` header) · `400`
bad request · `503` model not loaded yet · `500` internal error.
