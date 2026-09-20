# Persistent Conversations

By default, `/v1/chat/completions` is stateless — you resend the full
message history on every request (like OpenAI's API). For clients
that would rather let the server hold conversation state, FIREWING
also offers a stateful conversation API, backed by SQLite
(`firewing/inference/conversation_store.py`).

## Endpoints

```
POST   /v1/conversations                 create a conversation
GET    /v1/conversations                 list recent conversations
GET    /v1/conversations/{id}            fetch one, with full message history
POST   /v1/conversations/{id}/messages   send a message, get the reply
DELETE /v1/conversations/{id}            delete a conversation
```

## Example flow

```bash
# Create a conversation
curl -X POST http://localhost:8000/v1/conversations \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"title": "Trip planning"}'
# → {"conversation_id": "abc123...", ...}

# Send a message
curl -X POST http://localhost:8000/v1/conversations/abc123/messages \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "content": "Where should I visit in Lahore?"}}'

# Continue it later — no need to resend earlier turns
curl -X POST http://localhost:8000/v1/conversations/abc123/messages \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "content": "What about food?"}}'
```

## Scope and limitations

- Multimodal content (image parts) round-trips through storage fine
  (stored as JSON), but tool calling is **not** wired into the
  conversation-persistence endpoints in this beta — `/v1/conversations/{id}/messages`
  always calls `engine.generate()` without `tools`. Use the stateless
  `/v1/chat/completions` endpoint if you need tool calling.
- One SQLite file per deployment (`<data_dir>/conversations.db`) — fine
  for a single instance; if you run multiple replicas, point this at
  a real shared database instead (the `ConversationStore` interface is
  small on purpose, so that's a contained change).
- No per-user ownership/access control on conversations in this beta —
  any valid API key can read/continue/delete any conversation. If you
  need per-user isolation, that's the next thing to add here before
  using this with untrusted multi-tenant clients.
