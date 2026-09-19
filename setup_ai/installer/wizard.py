"""Interactive setup wizard: `python -m setup_ai.installer.wizard`
(also invoked by install.sh after the environment is bootstrapped).
"""

from __future__ import annotations

import subprocess
import sys

from firewing import MODEL_NAME

MENU = """\
========================================
        SETUP AI INSTALLER
        {model_name}
========================================

[1] Install FIREWING
[2] Update FIREWING
[3] Configure FIREWING
[4] Start FIREWING
[5] Stop FIREWING
[6] Restart FIREWING
[7] View Logs
[8] Check System
[9] Uninstall
[0] Exit
""".format(model_name=MODEL_NAME)


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"Command exited with code {result.returncode}", file=sys.stderr)


def action_install() -> None:
    _run(["bash", "install.sh"])


def action_update() -> None:
    _run(["setup-ai", "update"])


def action_configure() -> None:
    print("Edit configs/firewing.yaml (copy from configs/firewing.example.yaml if it doesn't exist yet).")
    print("Then set secrets in .env (copy from .env.example).")


def action_start() -> None:
    _run(["setup-ai", "start"])


def action_stop() -> None:
    _run(["setup-ai", "stop"])


def action_restart() -> None:
    _run(["setup-ai", "restart"])


def action_logs() -> None:
    _run(["setup-ai", "logs"])


def action_check_system() -> None:
    _run(["setup-ai", "doctor"])


def action_uninstall() -> None:
    print("Uninstall is intentionally manual in this beta to avoid accidental data loss.")
    print("See docs/troubleshooting.md for the manual uninstall steps.")


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
