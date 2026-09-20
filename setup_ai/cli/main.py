"""setup-ai CLI.

    setup-ai start | stop | restart | status | logs | update | config | model | doctor
    setup-ai chat
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from firewing import MODEL_NAME, __version__
# NOTE: firewing.config.settings imports `yaml`, and cmd_chat's imports pull
# in torch/transformers/fastapi. Those are NOT imported at module level here
# on purpose — a bare venv (no `pip install -r requirements.txt` yet) must
# still be able to run `setup-ai --help` and `setup-ai doctor` without a
# raw ModuleNotFoundError traceback. See _missing_deps_for() + main().


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
    "transformers": "transformers>=4.51",
    "fastapi": "fastapi>=0.110",
    "uvicorn": "uvicorn[standard]>=0.29",
    "pydantic": "pydantic>=2.6",
    "accelerate": "accelerate>=0.30",
}

# Commands that need more than the base `yaml` config loader.
_EXTRA_DEPS = {
    "chat": ["torch", "transformers"],
    "config": [],
    "model": [],
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

    print(f"Unknown model action: {action}", file=sys.stderr)
    return 1


def _update_model_config(config_path: str | None, model_path: str | None, adapter_path: str | None) -> None:
    """Patch model_path/adapter_path in the YAML config in place, preserving
    everything else. Falls back to configs/firewing.yaml if no path given."""
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


def cmd_chat(args: argparse.Namespace) -> int:
    import os as _os

    if getattr(args, "offline", False):
        # Tell huggingface_hub/transformers not to make any network calls —
        # only use what's already cached under ~/.cache/huggingface. This is
        # the "run locally, no internet needed" mode: it only works once the
        # model has been downloaded at least once with a network connection.
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
    try:
        loaded = load_model(settings.model)
    except ModelLoadError as exc:
        print(f"Failed to load model: {exc}", file=sys.stderr)
        if not getattr(args, "offline", False):
            print("If you're offline or Hugging Face is unreachable, this is expected — "
                  "run 'setup-ai doctor' to check connectivity.", file=sys.stderr)
        return 1

    engine = InferenceEngine(loaded, settings.model.max_context_tokens, settings.model.context_strategy)
    persona = load_personas()["default"]
    conversation = Conversation(system_prompt=persona.system_prompt)

    tool_registry = build_default_registry() if settings.model.enable_tool_calling else None
    if tool_registry:
        print(f"(tool calling enabled: {', '.join(t['function']['name'] for t in tool_registry.schemas())})")

    print("Type 'exit' to quit.\n")

    if getattr(args, "self_test", False):
        # Prove the pipeline is actually working end to end — send a fixed
        # "hi", show the same thinking indicator + streamed reply the
        # interactive loop uses, then fall through into the normal REPL.
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
            # First real token is ready — clear the "thinking..." line and
            # start printing the actual reply in its place.
            print("\r" + " " * len(thinking_label) + "\r", end="")
            print(f"{MODEL_NAME}: ", end="", flush=True)
            first = False
        print(chunk, end="", flush=True)
        reply_parts.append(chunk)
    if first:
        # Model produced no tokens at all (immediate EOS / max_tokens=0).
        print("\r" + " " * len(thinking_label) + "\r", end="")
        print(f"{MODEL_NAME}: (empty response — check max_tokens / the model checkpoint)", end="")
    print("\n")
    conversation.add_assistant("".join(reply_parts))


def _run_turn_with_tools(engine, conversation, params, tool_registry, max_hops: int = 3) -> None:
    """Non-streaming turn that lets the model call tools (possibly
    more than once) before producing its final answer. Streaming isn't
    used here since tool-call detection needs the complete response —
    see InferenceEngine.stream's docstring.
    """
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


def _systemctl(action: str) -> int:
    try:
        result = subprocess.run(["systemctl", action, "firewing"], check=False)
        return result.returncode
    except FileNotFoundError:
        print("systemctl not found. Are you on a systemd-based Linux system?", file=sys.stderr)
        return 1


def cmd_start(_args: argparse.Namespace) -> int:
    return _systemctl("start")


def cmd_stop(_args: argparse.Namespace) -> int:
    return _systemctl("stop")


def cmd_restart(_args: argparse.Namespace) -> int:
    return _systemctl("restart")


def cmd_status(_args: argparse.Namespace) -> int:
    return _systemctl("status")


def cmd_logs(_args: argparse.Namespace) -> int:
    try:
        subprocess.run(["journalctl", "-u", "firewing", "-f"], check=False)
        return 0
    except FileNotFoundError:
        print("journalctl not found.", file=sys.stderr)
        return 1


def cmd_update(_args: argparse.Namespace) -> int:
    print("Update flow placeholder: git pull + pip install -r requirements.txt + systemctl restart firewing")
    print("Wire this to your actual deployment method before using in production.")
    return 0


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
    ]:
        p = sub.add_parser(name)
        p.set_defaults(func=func)

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
    chat_parser.set_defaults(func=cmd_chat)

    # `model` has sub-actions (info/show | set | upgrade) instead of separate
    # top-level commands, since they all operate on the same config field.
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
    for p in (model_parser, model_info, model_show, model_set, model_upgrade):
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
