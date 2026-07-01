# SetupAI

A fully offline AI chat assistant built with Next.js. **No API key. No account. No server.
Nothing to "import" or clone from a model repo.** The language model itself runs entirely
inside your browser via [WebLLM](https://github.com/mlc-ai/web-llm) + WebGPU. The first
message triggers a one-time download of model weights into your browser's cache; every
run after that is fully offline.

> Built for the BlueTick Army / PGC toolset — same dark-navy + electric-blue, chrome-accent
> visual language as your other launcher and server projects, so it drops into that brand
> family cleanly. Rename freely if you want it standalone.

---

## Why this actually works with "no API key"

Most "AI chat app" tutorials secretly need `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in an
`.env` file, hitting a cloud endpoint. This one doesn't, because it doesn't call an API at
all — [`@mlc-ai/web-llm`](https://www.npmjs.com/package/@mlc-ai/web-llm) compiles a small
open-weight instruct model (Llama 3.2, Phi-3.5, Qwen2.5, or Gemma 2 — user's choice) to
WebAssembly/WebGPU and runs inference directly on the visitor's GPU, in-tab. That's the only
way to get genuinely offline, keyless AI in a web app today.

**The trade-off, stated plainly:** the browser needs WebGPU (current Chrome, Edge, or
Firefox Nightly) and a GPU with a few GB of free VRAM. There is no way around a model
download of some size on first use — "offline LLM" always means "downloaded once, run
locally," never "zero bytes, zero wait." The app is upfront about this with a live progress
meter instead of hiding it.

---

## Getting it running

```bash
npm install
npm run dev
```

Open `http://localhost:3000`, pick a model in the sidebar, send a message. The first send
downloads and compiles that model (progress bar shown); after that it's instant and works
with your Wi-Fi off.

```bash
npm run build && npm start   # production build
```

No environment variables. No `.env` file. Nothing to configure before first run.

## What's inside

```
app/            Next.js App Router: layout, page, global styles
components/     Sidebar, Composer, MessageBubble, ModelLoader
lib/            engine.ts (WebLLM wrapper), models.ts (catalog), storage.ts, types.ts
```

- **`lib/engine.ts`** — the entire "connect to the AI" surface. One singleton WebLLM engine,
  lazily created, streamed token-by-token, interruptible mid-generation.
- **`lib/models.ts`** — swap or extend the model catalog here. Any MLC-prebuilt model ID
  from the [WebLLM model list](https://github.com/mlc-ai/web-llm/blob/main/src/config.ts)
  works by adding one entry.

## Feature set

Rather than pad this list to hit a round number, here's what's actually implemented and
working end to end:

**Core chat**
- Streaming, token-by-token responses with stop/interrupt
- Regenerate last response
- Multi-turn context per conversation
- Editable per-conversation system prompt
- Markdown rendering: tables, lists, blockquotes, syntax-highlighted code blocks
- One-click copy on any message

**Model & runtime**
- 5 curated offline models spanning 1B–3B params (speed vs. quality trade-off, pick per device)
- Live download/compile progress meter with byte-accurate status text
- WebGPU capability detection with a clear fallback message if unsupported
- Model swap mid-session without losing conversation history

**Conversation management**
- Multiple conversations, auto-titled from the first message
- Persistent history via `localStorage` — survives refresh and browser restart
- Delete individual conversations
- Export any conversation to a `.md` file

**Design**
- Dark navy / electric-blue token system (`tailwind.config.ts`) — no default AI-app cream
  or acid-green palette
- Chakra Petch display type for headers, Inter for body, JetBrains Mono for code — set as
  CSS variables so re-theming is a one-file change
- Signature "model load meter" component instead of a generic spinner
- Full keyboard support, visible focus states, `prefers-reduced-motion` respected
- Responsive down to a single-column mobile layout

## Extending it

- **Add a model:** append an entry to `MODEL_OPTIONS` in `lib/models.ts` with a valid MLC
  model id.
- **Change the palette:** everything routes through the `ink` / `steel` / `volt` / `signal`
  color scales in `tailwind.config.ts`.
- **Swap fonts:** edit the three `next/font/google` calls in `app/layout.tsx`.
- **RAG / tool calls / attachments:** not included here to keep this a clean, honest
  starting point — `lib/engine.ts` is the single place to extend `streamChatCompletion`
  with tool definitions or a document-context prefix if you want to build that next.

## What changed in this update

**Fixes**
- **Race condition on model switch:** switching models while a previous one was still
  downloading could let the stale load "win" and silently install the wrong model. The
  loader now tracks a generation token and discards (and unloads) any load that's been
  superseded.
- **COEP header:** switched `Cross-Origin-Embedder-Policy` from `credentialless` to
  `require-corp` — the pairing WebLLM's own examples use, which more reliably unlocks
  `crossOriginIsolated` (needed for `SharedArrayBuffer`) across browsers. It only restricts
  embedded sub-resources, not the `fetch()` calls that download model weights, so this
  doesn't affect the offline download path.
- **Silent failures:** engine/model errors used to get buried as italic text inside a chat
  bubble. There's now a proper error banner above the composer with **Retry** and
  **Dismiss**, and the empty placeholder bubble is cleaned up instead of left blank.
- **Model dropdown during load:** it was only disabled while generating, so you could start
  switching models mid-download and cause the race above. Now disabled for the whole
  downloading/compiling window too.
- **Stuck loads:** added a reset/unload control (the power icon in the header) that fully
  releases the current model from GPU memory and returns to a clean `idle` state — useful
  if a load hangs or a model gets into a bad state.

**New features**
- **Live tokens/sec** shown in the header while generating, sourced directly from WebLLM's
  own usage stats.
- **Temperature and Top P sliders** per conversation, in the settings panel next to the
  system prompt.
- **Rename conversations** — click the pencil next to the chat title.
- **Unload/reset model** button — frees GPU memory without leaving the app.
- **Retry on failure** — one click re-runs the exact request that errored.

## Requirements

- Node.js 18.18+ for the dev/build tooling
- A WebGPU-capable browser for end users (Chrome/Edge 113+, Firefox Nightly with the flag on)
- No API key, no backend, no database
