# FIREWING Web UI

A single self-contained `index.html` chat interface — no build step
required. It talks to the FIREWING API's `/v1/chat/completions`
endpoint directly from the browser.

## Run it

Serve this directory with any static file server, or just open
`index.html` directly, then point it at your running FIREWING API
(default `http://localhost:8000`) and paste in an API key.

```bash
cd webui
python3 -m http.server 5173
# visit http://localhost:5173
```

**Note:** calling the API directly from a browser means your API key
is visible in that browser session's memory/network tab. That's fine
for local/personal use. For a multi-user deployment, put a thin
backend in front that holds the real key server-side instead of
shipping it to the browser — this UI doesn't do that yet (beta
limitation, see `docs/troubleshooting.md`).

## Design

Original layout and styling — not a copy of any existing AI product's
UI or branding. Supports: streaming responses, markdown + code block
rendering, dark mode (follows system preference), conversation history
(in-memory per session), system prompt / temperature / max-token
controls, model selector (currently a single model).
