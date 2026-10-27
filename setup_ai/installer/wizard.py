"""Interactive setup wizard: `python -m setup_ai.installer.wizard`
(also invoked by install.sh after the environment is bootstrapped).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from firewing import MODEL_NAME

MENU = """\
========================================
        SETUP AI INSTALLER
        {model_name}
========================================

[1] Install / Reinstall FIREWING
[2] Update FIREWING
[3] Configure FIREWING
[4] Start FIREWING (Service)
[5] Stop FIREWING (Service)
[6] Restart FIREWING (Service)
[7] View Logs
[8] Check System / Doctor
[9] Uninstall FIREWING
[C] Interactive Chat (CLI)
[S] Serve API Server (Local)
[0] Exit
""".format(model_name=MODEL_NAME)


def _cli(subcmd: list[str]) -> None:
    cmd = [sys.executable, "-m", "setup_ai.cli.main"] + subcmd
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"Command exited with code {result.returncode}", file=sys.stderr)


def action_install() -> None:
    if Path("install.sh").exists():
        bash = shutil.which("bash") or "bash"
        subprocess.run([bash, "install.sh"], check=False)
    else:
        print("install.sh not found in the current directory.", file=sys.stderr)


def action_update() -> None:
    _cli(["update"])


def action_configure() -> None:
    print("\nConfiguration files:")
    print("1. configs/firewing.yaml (copy from configs/firewing.example.yaml)")
    print("2. .env (copy from .env.example for API keys and secrets)")
    if not Path("configs/firewing.yaml").exists() and Path("configs/firewing.example.yaml").exists():
        shutil.copy("configs/firewing.example.yaml", "configs/firewing.yaml")
        print("  -> Created configs/firewing.yaml from example.")
    if not Path(".env").exists() and Path(".env.example").exists():
        shutil.copy(".env.example", ".env")
        print("  -> Created .env from example.")


def action_start() -> None:
    _cli(["start"])


def action_stop() -> None:
    _cli(["stop"])


def action_restart() -> None:
    _cli(["restart"])


def action_logs() -> None:
    _cli(["logs"])


def action_check_system() -> None:
    _cli(["doctor"])


def action_chat() -> None:
    _cli(["chat"])


def action_serve() -> None:
    _cli(["serve"])


def action_uninstall() -> None:
    if Path("uninstall.sh").exists():
        confirm = input("Are you sure you want to uninstall FIREWING? [y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            bash = shutil.which("bash") or "bash"
            subprocess.run([bash, "uninstall.sh"], check=False)
            return
    print("See docs/troubleshooting.md for manual removal instructions.")


ACTIONS = {
    "1": action_install,
    "2": action_update,
    "3": action_configure,
    "4": action_start,
    "5": action_stop,
    "6": action_restart,
    "7": action_logs,
    "8": action_check_system,
    "9": action_uninstall,
    "c": action_chat,
    "C": action_chat,
    "s": action_serve,
    "S": action_serve,
}


def main() -> int:
    while True:
        print(MENU)
        choice = input("Select an option: ").strip()
        if choice == "0":
            print("Goodbye.")
            return 0
        action = ACTIONS.get(choice)
        if action is None:
            print(f"Unrecognized option '{choice}'.\n")
            continue
        action()
        print()


if __name__ == "__main__":
    sys.exit(main())
