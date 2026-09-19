"""setup-ai CLI.

    setup-ai start | stop | restart | status | logs | update | config | model | doctor
    setup-ai chat
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from firewing import MODEL_NAME, __version__
from firewing.config.settings import load_settings


BANNER = f"""\
========================================
        SETUP AI
        {MODEL_NAME}
========================================
"""


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
        print("GPU:           none detected (CPU-only inference)")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    print(f"model_path:  {settings.model.model_path}")
    print(f"device:      {settings.model.device}")
    print(f"quantization:{settings.model.quantization}")
    print(f"api.port:    {settings.api.port}")
    print(f"api.require_api_key: {settings.api.require_api_key}")
    return 0


def cmd_model(_args: argparse.Namespace) -> int:
    from firewing import UPSTREAM_BASE_MODEL, UPSTREAM_LICENSE

    print(f"Base model:  {UPSTREAM_BASE_MODEL}")
    print(f"License:     {UPSTREAM_LICENSE}")
    print("FIREWING is not independently trained — see /NOTICE for full attribution.")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from firewing.config.settings import load_settings
    from firewing.model.loader import load_model, ModelLoadError
    from firewing.inference.engine import InferenceEngine, GenerationParams
    from firewing.inference.conversation import Conversation
    from firewing.inference.personas import load_personas

    print(BANNER)
    settings = load_settings(args.config)
    try:
        loaded = load_model(settings.model)
    except ModelLoadError as exc:
        print(f"Failed to load model: {exc}", file=sys.stderr)
        return 1

    engine = InferenceEngine(loaded, settings.model.max_context_tokens, settings.model.context_strategy)
    persona = load_personas()["default"]
    conversation = Conversation(system_prompt=persona.system_prompt)

    print("Type 'exit' to quit.\n")
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break

        conversation.add_user(user_input)
        print(f"\n{MODEL_NAME}: ", end="", flush=True)
        params = GenerationParams(temperature=persona.temperature, top_p=persona.top_p)
        reply_parts = []
        for chunk in engine.stream(conversation, params):
            print(chunk, end="", flush=True)
            reply_parts.append(chunk)
        print("\n")
        conversation.add_assistant("".join(reply_parts))
    return 0


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
        ("model", cmd_model),
        ("doctor", cmd_doctor),
        ("chat", cmd_chat),
    ]:
        p = sub.add_parser(name)
        p.set_defaults(func=func)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
