# API Reference

Base URL: `http://<host>:8000` (put behind nginx + TLS for production —
see `docs/vps.md`).

Auth: `Authorization: Bearer <api_key>` on every endpoint marked
"authenticated" below. Keys are set via `FIREWING_API_KEYS`.

## `GET /health`
Unauthenticated. Liveness check for Docker/systemd/nginx.

```json
{"status": "ok", "version": "1.0.0-beta"}
```

## `GET /v1/models`
Unauthenticated. Lists available models.

## `GET /v1/system` (authenticated)
Hardware/runtime info: OS, CPU, RAM, GPU, VRAM, CUDA version, Docker availability.

## `GET /v1/status` (authenticated)
Basic status: model name, version, running state.

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
schema — see [Function / Tool Calling](tool-calling.md) (note:
`tools` + `stream: true` together return 400 in this beta).

Non-streaming response:
```json
{
  "id": "req_...",
  "object": "chat.completion",
  "model": "firewing-1.0-beta",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}
  ]
}
```

Streaming (`"stream": true`): Server-Sent Events, `data: <chunk>` per
token/segment, terminated by `data: [DONE]`.

## Persistent conversations (authenticated)

See [Persistent Conversations](conversations.md) for the full
`/v1/conversations` API (create/list/get/delete, and
`POST /v1/conversations/{id}/messages` for server-held chat history).

## Admin API (requires `FIREWING_ADMIN_KEY`, not a regular API key)

### `POST /v1/admin/keys`
Create a new API key. Request: `{"label": "mobile app"}`. Response
includes the plaintext key **exactly once** — it's only ever stored
hashed after this.

### `GET /v1/admin/keys`
List keys (label, id, created_at, revoked — never the key itself).

### `DELETE /v1/admin/keys/{key_id}`
Revoke a key. Revoked keys are kept (for audit) but no longer accepted.

### `GET /v1/admin/stats`
Aggregate request stats: uptime, recent request/error counts, average
latency. In-memory, per-process (see `docs/troubleshooting.md`).

A basic dashboard for these is in `webui/admin.html`.

## Errors

All errors return:
```json
{"error": {"type": "...", "message": "...", "request_id": "req_..."}}
```

`401` invalid/missing API key · `429` rate limit exceeded · `400`
bad request (e.g. `max_tokens` over server limit) · `503` model not
loaded yet · `500` internal error (details are logged server-side with
the `request_id`, never returned to the client).
