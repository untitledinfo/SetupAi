"""setup-ai CLI.

    setup-ai start | stop | restart | status | logs | update | config | model | doctor
    setup-ai chat
    setup-ai keys
    setup-ai conv
    setup-ai bench
    setup-ai serve
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from firewing import MODEL_NAME, __version__

BANNER = f"""\
========================================
        SETUP AI
        {MODEL_NAME}
========================================
"""

# Every package requirements.txt installs that at least one subcommand
# needs, mapped to (import name -> pip spec) so a clean message can name
# the exact fix instead of just "something is missing".
_PIP_SPEC = {
    "yaml": "pyyaml>=6.0",
    "torch": "torch>=2.2",
    "transformers": "transformers>=4.57.0",
    "fastapi": "fastapi>=0.110",
    "uvicorn": "uvicorn[standard]>=0.29",
    "pydantic": "pydantic>=2.6",
    "accelerate": "accelerate>=0.30",
    "huggingface_hub": "huggingface_hub>=0.24",
}

# Commands that need more than the base `yaml` config loader.
_EXTRA_DEPS = {
    "chat": ["torch", "transformers"],
    "bench": ["torch", "transformers"],
    "serve": ["uvicorn", "fastapi"],
    "config": [],
    "model": [],
    "keys": [],
    "conv": [],
}


def _missing_deps_for(command: str) -> list[str]:
    needed = ["yaml"] + _EXTRA_DEPS.get(command, [])
    missing = []
    for mod in needed:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


def _dep_error(missing: list[str]) -> None:
    print(f"Missing required package(s): {', '.join(missing)}", file=sys.stderr)
    print(file=sys.stderr)
    print("Fix:", file=sys.stderr)
    print("  pip install -r requirements.txt", file=sys.stderr)
    print(file=sys.stderr)
    print("If you haven't set up a virtual environment yet:", file=sys.stderr)
    print("  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt", file=sys.stderr)
    print(file=sys.stderr)
    print("Or let the installer verify/fix this for you: sudo bash install.sh (works in containers too — it", file=sys.stderr)
    print("auto-detects no systemd and falls back to a local venv install instead of failing).", file=sys.stderr)


def cmd_doctor(_args: argparse.Namespace) -> int:
    from firewing.utils.system_info import get_system_info

    info = get_system_info()
    print(f"OS:            {info.os_name} {info.os_version}")
    print(f"Python:        {info.python_version}")
    print(f"CPU cores:     {info.cpu_count}")
    print(f"RAM:           {info.total_ram_mb} MB" if info.total_ram_mb else "RAM:           unknown")
    print(f"Free disk:     {info.free_disk_mb} MB" if info.free_disk_mb else "Free disk:     unknown")
    print(f"Docker:        {'available' if info.docker_available else 'NOT FOUND'}")
    if info.gpu.available:
        print(f"GPU:           {info.gpu.name} ({info.gpu.free_vram_mb}/{info.gpu.total_vram_mb} MB free)")
        print(f"CUDA:          {info.gpu.cuda_version or 'unknown'}")
    else:
        print("GPU:           none detected (CPU-only inference — the 30B base model will be very slow)")

    print()
    print("Python packages:")
    for mod, spec in _PIP_SPEC.items():
        try:
            __import__(mod)
            print(f"  [ok]      {mod}")
        except ImportError:
            print(f"  [missing] {mod}   (pip install '{spec}')")

    print()
    print("Config files:")
    for path in ("configs/firewing.yaml", ".env"):
        print(f"  [{'ok' if __import__('os').path.exists(path) else 'MISSING'}]  {path}")

    print()
    print("Internet reachability (huggingface.co, for downloading model weights):")
    import socket

    try:
        socket.create_connection(("huggingface.co", 443), timeout=3).close()
        print("  [ok]      reachable")
    except OSError as exc:
        print(f"  [no]      not reachable ({exc}) — offline is fine only if the model is already cached locally")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    from firewing.config.settings import load_settings

    settings = load_settings(args.config)
    print(f"model_path:  {settings.model.model_path}")
    print(f"device:      {settings.model.device}")
    print(f"quantization:{settings.model.quantization}")
    print(f"api.port:    {settings.api.port}")
    print(f"api.require_api_key: {settings.api.require_api_key}")
    return 0


def cmd_model(args: argparse.Namespace) -> int:
    from firewing import UPSTREAM_BASE_MODEL, UPSTREAM_LICENSE
    from firewing.config.settings import load_settings

    action = getattr(args, "model_action", None) or "info"

    if action in ("info", "show"):
        settings = load_settings(args.config)
        print(f"Upstream base: {UPSTREAM_BASE_MODEL}")
        print(f"License:       {UPSTREAM_LICENSE}")
        print(f"Configured model_path: {settings.model.model_path}")
        print(f"Configured adapter_path (LoRA): {settings.model.adapter_path or '(none)'}")
        print(
            "FIREWING is not an independently trained model — it serves the "
            "upstream weights above. See /NOTICE and docs/model-card.md for full "
            "attribution. To make the served model genuinely yours, fine-tune a "
            "LoRA adapter (docs/training.md) and set it with "
            "'setup-ai model set --adapter <path>', rather than claiming the base "
            "weights themselves as your own."
        )
        return 0

    if action == "set":
        if not args.path and not args.adapter:
            print("Provide --path (base model repo id/local path) and/or --adapter (LoRA adapter path).", file=sys.stderr)
            return 1
        _update_model_config(args.config, model_path=args.path, adapter_path=args.adapter)
        print("Updated model configuration. Restart the service to apply:")
        print("  sudo systemctl restart firewing   (or: setup-ai restart)")
        return 0

    if action == "upgrade":
        print(f"Currently configured base model: {load_settings(args.config).model.model_path}")
        print("FIREWING itself has no separate 'upgrade' channel for the base model —")
        print("'upgrading' means pointing at a newer upstream revision or your own")
        print("checkpoint. This:")
        print("  1. Re-downloads/validates the target model via 'transformers' on first load")
        print("  2. Updates configs/firewing.yaml's model_path")
        print("  3. Leaves your LoRA adapter_path untouched unless you also pass --adapter")
        if not args.path:
            print("\nRun again with --path <hf-repo-or-local-path> to actually perform the upgrade.")
            return 0
        _update_model_config(args.config, model_path=args.path, adapter_path=args.adapter)
        print(f"\nmodel_path set to: {args.path}")
        print("Restart the service to load it: sudo systemctl restart firewing")
        return 0

    if action in ("list", "search"):
        return cmd_model_browse(args)

    print(f"Unknown model action: {action}", file=sys.stderr)
    return 1


def cmd_model_browse(args: argparse.Namespace) -> int:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("Missing required package: huggingface_hub", file=sys.stderr)
        print("Fix: pip install -U huggingface_hub", file=sys.stderr)
        return 1

    query = getattr(args, "query", None)
    limit = getattr(args, "limit", None) or 20
    task = getattr(args, "task", None)

    kwargs: dict = {"limit": limit, "sort": "downloads"}
    if query:
        kwargs["search"] = query
    if task:
        kwargs["pipeline_tag"] = task
    elif not query:
        kwargs["pipeline_tag"] = "text-generation"

    label = "Browsing" if not query else f"Searching for {query!r}"
    print(f"{label} on huggingface.co"
          + (f" (pipeline_tag={task})" if task else "")
          + " ... (public, no API key needed — set HF_TOKEN only for higher rate "
            "limits or gated/private repos)")

    api = HfApi()
    try:
        results = list(api.list_models(**kwargs))
    except Exception as exc:
        print(f"Could not reach Hugging Face Hub: {exc}", file=sys.stderr)
        print("Run 'setup-ai doctor' to check connectivity.", file=sys.stderr)
        return 1

    if not results:
        print("No models found. Try a different --task or search term.")
        return 0

    print(f"\n{'MODEL ID':<55} {'DOWNLOADS':>10} {'LIKES':>6}  GATED")
    print("-" * 82)
    for m in results:
        downloads = getattr(m, "downloads", None)
        likes = getattr(m, "likes", None)
        gated = getattr(m, "gated", False)
        print(
            f"{m.id:<55} "
            f"{downloads if downloads is not None else '-':>10} "
            f"{likes if likes is not None else '-':>6}  "
            f"{'yes' if gated else 'no'}"
        )
    print("\nUse one of these with:")
    print("  setup-ai model set --path <MODEL ID>")
    print("(gated repos also need: huggingface-cli login, or export HF_TOKEN=...)")
    return 0


def _update_model_config(config_path: str | None, model_path: str | None, adapter_path: str | None) -> None:
    import yaml

    path = config_path or "configs/firewing.yaml"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        data = {}

    data.setdefault("model", {})
    if model_path:
        data["model"]["model_path"] = model_path
    if adapter_path:
        data["model"]["adapter_path"] = adapter_path

    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


_KNOWN_MODEL_VRAM_GB = {
    "qwen/qwen3-omni-30b-a3b-instruct": {"bfloat16": 62, "float16": 62, "float32": 124, "int8": 32, "int4": 18},
    "qwen/qwen3-omni-30b-a3b-thinking": {"bfloat16": 62, "float16": 62, "float32": 124, "int8": 32, "int4": 18},
    "qwen/qwen3-omni-30b-a3b-captioner": {"bfloat16": 62, "float16": 62, "float32": 124, "int8": 32, "int4": 18},
}


def _maybe_warn_hardware(model_cfg) -> None:
    try:
        from firewing.model.loader import _resolve_device, _resolve_dtype
        from firewing.utils.system_info import get_system_info

        info = get_system_info()
        device = _resolve_device(model_cfg.device)
        dtype = _resolve_dtype(model_cfg.dtype, device)
        needed_gb = _KNOWN_MODEL_VRAM_GB.get(model_cfg.model_path.lower(), {}).get(
            model_cfg.quantization or dtype
        )
        if needed_gb is None:
            return

        if device.startswith("cuda") and info.gpu.available and info.gpu.free_vram_mb:
            free_gb = info.gpu.free_vram_mb / 1024
            if free_gb < needed_gb:
                print(
                    f"Heads up: {model_cfg.model_path} needs roughly {needed_gb} GB of VRAM at "
                    f"{model_cfg.quantization or dtype}, but only ~{free_gb:.1f} GB free was "
                    "detected on this GPU. It may fail with an out-of-memory error. Try: set "
                    "'quantization: int4' in configs/firewing.yaml, or pick a smaller model with "
                    "'setup-ai model search <keyword>'."
                )
        elif not device.startswith("cuda") and info.total_ram_mb:
            ram_gb = info.total_ram_mb / 1024
            if ram_gb < needed_gb:
                print(
                    f"Heads up: {model_cfg.model_path} needs roughly {needed_gb} GB of RAM to run "
                    f"on CPU at {model_cfg.quantization or dtype}, but only ~{ram_gb:.1f} GB total "
                    "RAM was detected. This will likely be extremely slow or fail. Try: set "
                    "'quantization: int4', or pick a smaller model with 'setup-ai model search "
                    "<keyword>'."
                )
    except Exception:
        pass


def cmd_chat(args: argparse.Namespace) -> int:
    import os as _os

    if getattr(args, "offline", False):
        _os.environ["HF_HUB_OFFLINE"] = "1"
        _os.environ["TRANSFORMERS_OFFLINE"] = "1"
        print("(offline mode: will only use already-cached model files, no network calls)")

    from firewing.config.settings import load_settings
    from firewing.model.loader import load_model, ModelLoadError
    from firewing.inference.engine import InferenceEngine, GenerationParams
    from firewing.inference.conversation import Conversation
    from firewing.inference.personas import load_personas
    from firewing.inference.tools import build_default_registry

    print(BANNER)
    settings = load_settings(args.config)
    print(f"Loading model: {settings.model.model_path}"
          + (f" + adapter {settings.model.adapter_path}" if settings.model.adapter_path else "")
          + " ... (first run downloads the weights and can take a while)")
    _maybe_warn_hardware(settings.model)

    try:
        loaded = load_model(settings.model)
    except ModelLoadError as exc:
        print(f"Failed to load model: {exc}", file=sys.stderr)
        if not getattr(args, "offline", False):
            print("If you're offline or Hugging Face is unreachable, this is expected — "
                  "run 'setup-ai doctor' to check connectivity.", file=sys.stderr)
        return 1

    engine = InferenceEngine(loaded, settings.model.max_context_tokens, settings.model.context_strategy)
    personas = load_personas()
    persona_name = getattr(args, "persona", None) or "default"
    persona = personas.get(persona_name, personas["default"])
    conversation = Conversation(system_prompt=persona.system_prompt)

    tool_registry = build_default_registry() if settings.model.enable_tool_calling else None
    if tool_registry:
        print(f"(tool calling enabled: {', '.join(t['function']['name'] for t in tool_registry.schemas())})")

    print(f"(persona: {persona.name})")
    print("Type 'exit' to quit.\n")

    if getattr(args, "self_test", False):
        print("You: hi   (automatic self-test)")
        conversation.add_user("hi")
        params = GenerationParams(temperature=persona.temperature, top_p=persona.top_p)
        if tool_registry:
            _run_turn_with_tools(engine, conversation, params, tool_registry)
        else:
            _run_turn_streaming(engine, conversation, params)
        print(f"Self-test passed — {MODEL_NAME} is loaded and replying. Continuing to chat below.\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break

        conversation.add_user(user_input)
        params = GenerationParams(temperature=persona.temperature, top_p=persona.top_p)

        if tool_registry:
            _run_turn_with_tools(engine, conversation, params, tool_registry)
        else:
            _run_turn_streaming(engine, conversation, params)
    return 0


def _run_turn_streaming(engine, conversation, params) -> None:
    thinking_label = f"\n{MODEL_NAME} is thinking..."
    print(thinking_label, end="", flush=True)
    reply_parts: list[str] = []
    first = True
    for chunk in engine.stream(conversation, params):
        if first:
            print("\r" + " " * len(thinking_label) + "\r", end="")
            print(f"{MODEL_NAME}: ", end="", flush=True)
            first = False
        print(chunk, end="", flush=True)
        reply_parts.append(chunk)
    if first:
        print("\r" + " " * len(thinking_label) + "\r", end="")
        print(f"{MODEL_NAME}: (empty response — check max_tokens / the model checkpoint)", end="")
    print("\n")
    conversation.add_assistant("".join(reply_parts))


def _run_turn_with_tools(engine, conversation, params, tool_registry, max_hops: int = 3) -> None:
    tools = tool_registry.schemas()
    for _ in range(max_hops):
        thinking_label = f"\n{MODEL_NAME} is thinking..."
        print(thinking_label, end="", flush=True)
        result = engine.generate(conversation, params, tools=tools)
        print("\r" + " " * len(thinking_label) + "\r", end="")

        if not result.tool_calls:
            print(f"{MODEL_NAME}: {result.text}\n")
            conversation.add_assistant(result.text)
            return

        conversation.add_assistant(result.text or "")
        for call in result.tool_calls:
            print(f"[calling tool: {call.name}({call.arguments})]")
            tool_result = tool_registry.execute(call)
            print(f"[tool result: {tool_result}]")
            conversation.add_tool_result(call.id, call.name, tool_result)

    print(f"\n{MODEL_NAME}: (stopped after {max_hops} tool calls without a final answer)\n")


def cmd_keys(args: argparse.Namespace) -> int:
    from firewing.config.settings import load_settings
    from firewing.api.security.key_store import KeyStore

    settings = load_settings(args.config)
    store = KeyStore(f"{settings.data_dir}/api_keys.json")
    action = getattr(args, "keys_action", None) or "list"

    if action == "list":
        keys = store.list_keys()
        if not keys:
            print("No API keys configured.")
            return 0
        print(f"\n{'LABEL':<25} {'KEY ID':<18} {'CREATED':<22} {'STATUS':<10} {'REQUESTS':<10}")
        print("-" * 88)
        for k in keys:
            created_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(k.created_at))
            status_str = "revoked" if k.revoked else "active"
            print(f"{k.label:<25} {k.key_id:<18} {created_str:<22} {status_str:<10} {k.request_count:<10}")
        return 0

    if action == "create":
        label = args.label
        plaintext, record = store.create_key(label)
        print(f"\nCreated key '{label}':")
        print(f"  Key ID:     {record.key_id}")
        print(f"  API Key:    {plaintext}")
        print("\nSave this key now — it is hashed in storage and cannot be shown again.")
        return 0

    if action == "revoke":
        if store.revoke_key(args.key_id):
            print(f"Key {args.key_id} has been revoked.")
            return 0
        print(f"Key {args.key_id} not found.", file=sys.stderr)
        return 1

    if action == "delete":
        if store.delete_key(args.key_id):
            print(f"Key {args.key_id} permanently deleted.")
            return 0
        print(f"Key {args.key_id} not found.", file=sys.stderr)
        return 1

    print(f"Unknown keys action: {action}", file=sys.stderr)
    return 1


def cmd_conv(args: argparse.Namespace) -> int:
    from firewing.config.settings import load_settings
    from firewing.inference.conversation_store import ConversationStore

    settings = load_settings(args.config)
    store = ConversationStore(f"{settings.data_dir}/conversations.db")
    action = getattr(args, "conv_action", None) or "list"

    if action == "list":
        convs = store.list()
        if not convs:
            print("No persistent conversations found.")
            return 0
        print(f"\n{'ID':<34} {'UPDATED':<20} {'PERSONA':<12} TITLE")
        print("-" * 85)
        for c in convs:
            up_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.updated_at))
            print(f"{c.conversation_id:<34} {up_str:<20} {(c.persona or 'default'):<12} {c.title}")
        return 0

    if action == "show":
        rec = store.get(args.conversation_id)
        if not rec:
            print(f"Conversation {args.conversation_id} not found.", file=sys.stderr)
            return 1
        print(f"=== Conversation: {rec.title} ({rec.conversation_id}) ===")
        print(f"Persona: {rec.persona or 'default'}")
        print(f"Messages: {len(rec.messages)}\n")
        for m in rec.messages:
            print(f"[{m.role.upper()}]:")
            print(f"{m.content}\n")
        return 0

    if action == "delete":
        if store.delete(args.conversation_id):
            print(f"Conversation {args.conversation_id} deleted.")
            return 0
        print(f"Conversation {args.conversation_id} not found.", file=sys.stderr)
        return 1

    if action == "export":
        md = store.export_markdown(args.conversation_id)
        if not md:
            print(f"Conversation {args.conversation_id} not found.", file=sys.stderr)
            return 1
        if getattr(args, "out", None):
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"Exported conversation to {args.out}")
        else:
            print(md)
        return 0

    print(f"Unknown conv action: {action}", file=sys.stderr)
    return 1


def cmd_bench(args: argparse.Namespace) -> int:
    from scripts.bench.benchmark import run_benchmark

    prompt = getattr(args, "prompt", "Explain how photosynthesis works in three sentences.")
    max_tokens = getattr(args, "max_tokens", 256)
    run_benchmark(prompt, max_tokens, args.config)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    from firewing.config.settings import load_settings

    settings = load_settings(args.config)
    host = getattr(args, "host", None) or settings.api.host
    port = getattr(args, "port", None) or settings.api.port
    reload = getattr(args, "reload", False)
    workers = getattr(args, "workers", 1)

    print(f"Starting FIREWING API server on http://{host}:{port} ...")
    uvicorn.run(
        "firewing.api.server:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )
    return 0


def _systemctl(action: str) -> int:
    try:
        result = subprocess.run(["systemctl", action, "firewing"], check=False)
        return result.returncode
    except FileNotFoundError:
        return -1


def cmd_start(_args: argparse.Namespace) -> int:
    res = _systemctl("start")
    if res == -1:
        print("systemctl not found. Use 'setup-ai serve' to run the API server directly.", file=sys.stderr)
        return 1
    return res


def cmd_stop(_args: argparse.Namespace) -> int:
    res = _systemctl("stop")
    if res == -1:
        print("systemctl not found. Terminate the running server process directly.", file=sys.stderr)
        return 1
    return res


def cmd_restart(_args: argparse.Namespace) -> int:
    res = _systemctl("restart")
    if res == -1:
        print("systemctl not found.", file=sys.stderr)
        return 1
    return res


def cmd_status(args: argparse.Namespace) -> int:
    res = _systemctl("status")
    if res == 0:
        return 0

    # Fall back to checking local API HTTP server
    from firewing.config.settings import load_settings
    import urllib.request
    import json

    settings = load_settings(args.config)
    host = "127.0.0.1" if settings.api.host in ("0.0.0.0", "") else settings.api.host
    url = f"http://{host}:{settings.api.port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            print(f"FIREWING API server is running on http://{host}:{settings.api.port}")
            print(f"  Status:       {data.get('status')}")
            print(f"  Version:      {data.get('version')}")
            print(f"  Model loaded: {data.get('model_loaded')}")
            return 0
    except Exception:
        print(f"FIREWING service is not active and API is not responding on port {settings.api.port}.")
        return 1


def cmd_logs(_args: argparse.Namespace) -> int:
    try:
        subprocess.run(["journalctl", "-u", "firewing", "-f"], check=False)
        return 0
    except FileNotFoundError:
        print("journalctl not found. Check local log files in /var/log/firewing or console output.", file=sys.stderr)
        return 1


def cmd_update(_args: argparse.Namespace) -> int:
    print("Checking repository for updates...")
    try:
        subprocess.run(["git", "pull"], check=False)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=False)
        _systemctl("restart")
        print("Update complete.")
        return 0
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="setup-ai", description=BANNER)
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--version", action="version", version=f"setup-ai / {MODEL_NAME} {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in [
        ("start", cmd_start),
        ("stop", cmd_stop),
        ("restart", cmd_restart),
        ("status", cmd_status),
        ("logs", cmd_logs),
        ("update", cmd_update),
        ("config", cmd_config),
        ("doctor", cmd_doctor),
        ("bench", cmd_bench),
    ]:
        p = sub.add_parser(name)
        p.set_defaults(func=func)

    # `serve` command
    serve_parser = sub.add_parser("serve", help="Run the FIREWING API server locally")
    serve_parser.add_argument("--host", default=None, help="Bind host (default: from config)")
    serve_parser.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code change")
    serve_parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    serve_parser.set_defaults(func=cmd_serve)

    chat_parser = sub.add_parser("chat", help="Interactive REPL against the local model")
    chat_parser.add_argument(
        "--offline", action="store_true",
        help="Don't contact Hugging Face at all — use only what's already cached locally",
    )
    chat_parser.add_argument(
        "--self-test", action="store_true", dest="self_test",
        help="Send a fixed 'hi' first, show thinking + reply, then continue into the normal REPL "
             "— proves the model is actually loaded and generating before you type anything",
    )
    chat_parser.add_argument("--persona", default="default", help="Persona preset to use")
    chat_parser.set_defaults(func=cmd_chat)

    # `keys` command
    keys_parser = sub.add_parser("keys", help="Manage multi-user API keys")
    keys_sub = keys_parser.add_subparsers(dest="keys_action")
    keys_list = keys_sub.add_parser("list", help="List all API keys")
    keys_create = keys_sub.add_parser("create", help="Generate a new API key")
    keys_create.add_argument("label", help="Label or owner of the new key")
    keys_revoke = keys_sub.add_parser("revoke", help="Revoke an existing API key")
    keys_revoke.add_argument("key_id", help="Hex key_id to revoke")
    keys_delete = keys_sub.add_parser("delete", help="Permanently delete an API key")
    keys_delete.add_argument("key_id", help="Hex key_id to delete")
    for p in (keys_parser, keys_list, keys_create, keys_revoke, keys_delete):
        p.set_defaults(func=cmd_keys)

    # `conv` command
    conv_parser = sub.add_parser("conv", help="Manage persistent server conversations")
    conv_sub = conv_parser.add_subparsers(dest="conv_action")
    conv_list = conv_sub.add_parser("list", help="List recent conversations")
    conv_show = conv_sub.add_parser("show", help="Show full conversation transcript")
    conv_show.add_argument("conversation_id", help="Conversation ID to view")
    conv_delete = conv_sub.add_parser("delete", help="Delete a conversation")
    conv_delete.add_argument("conversation_id", help="Conversation ID to delete")
    conv_export = conv_sub.add_parser("export", help="Export a conversation as markdown")
    conv_export.add_argument("conversation_id", help="Conversation ID to export")
    conv_export.add_argument("--out", default=None, help="Save to markdown file instead of stdout")
    for p in (conv_parser, conv_list, conv_show, conv_delete, conv_export):
        p.set_defaults(func=cmd_conv)

    # `model` subcommands
    model_parser = sub.add_parser("model", help="Inspect or change the served base model / LoRA adapter")
    model_sub = model_parser.add_subparsers(dest="model_action")
    model_info = model_sub.add_parser("info", help="Show the currently configured model (default)")
    model_show = model_sub.add_parser("show", help="Alias for 'info'")
    model_set = model_sub.add_parser("set", help="Point FIREWING at a different base model and/or LoRA adapter")
    model_set.add_argument("--path", help="HF repo id or local path for the base model")
    model_set.add_argument("--adapter", help="Path to a trained LoRA adapter (see docs/training.md)")
    model_upgrade = model_sub.add_parser("upgrade", help="Upgrade/replace the served base model")
    model_upgrade.add_argument("--path", help="HF repo id or local path for the new base model")
    model_upgrade.add_argument("--adapter", help="Path to a trained LoRA adapter to keep applied")
    model_list = model_sub.add_parser(
        "list", help="Browse popular public models on the Hugging Face Hub (no API key needed)"
    )
    model_list.add_argument("--limit", type=int, default=20, help="Max results to show (default 20)")
    model_list.add_argument(
        "--task", default=None,
        help="Filter by HF pipeline_tag, e.g. text-generation, image-text-to-text, any-to-any",
    )
    model_search = model_sub.add_parser(
        "search", help="Search the Hugging Face Hub by keyword (no API key needed)"
    )
    model_search.add_argument("query", help="Keyword to search for, e.g. qwen, llama, omni")
    model_search.add_argument("--limit", type=int, default=20, help="Max results to show (default 20)")
    model_search.add_argument("--task", default=None, help="Filter by HF pipeline_tag")
    for p in (model_parser, model_info, model_show, model_set, model_upgrade, model_list, model_search):
        p.set_defaults(func=cmd_model)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    missing = _missing_deps_for(args.command)
    if missing:
        _dep_error(missing)
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
