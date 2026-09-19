# Quickstart

```bash
git clone <repository>
cd setup-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp configs/firewing.example.yaml configs/firewing.yaml
cp .env.example .env
```

Set at least one API key in `.env`:

```
FIREWING_API_KEYS=your-generated-key-here
```

## Chat from the CLI

```bash
python -m setup_ai.cli.main chat
```

```
========================================
        SETUP AI
        FIREWING 1.0 BETA
========================================

Type 'exit' to quit.

You: Hello
FIREWING: Hello! How can I help you today?
```

## Or run the API

```bash
uvicorn firewing.api.server:app --reload
```

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your-generated-key-here" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

Note: the first request that actually loads the model needs the real
Qwen3-Omni weights downloaded (either via Hugging Face automatically,
or pointed at a local path in `configs/firewing.yaml` under
`model.model_path`). See `docs/vps.md` / `docs/gpu.md` for hardware
sizing before attempting this on a small instance.
