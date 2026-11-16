from __future__ import annotations

import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.runtime_console.tui_v2 import main


def launch_tui(argv: List[str] | None = None, *, force_run: bool = False) -> int:
    """Shared TUI entrypoint used by both `apps/sentrybot_tui.py` and `apps/run_robot_tui.py`."""
    cli_args = list(argv if argv is not None else sys.argv[1:])
    prefix = ["--root", str(ROOT)]
    if force_run and "--run" not in cli_args and "--no-run" not in cli_args:
        prefix.append("--run")
    return main(prefix + cli_args)


if __name__ == "__main__":
    raise SystemExit(launch_tui())
