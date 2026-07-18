from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _probe_import(module: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_light_agent_core_imports_do_not_initialize_runtime_console():
    modules = [
        "modules.agent_core",
        "modules.agent_core.services",
        "modules.agent_core.services.memory",
        "modules.agent_core.services.memory_consolidator",
        "modules.agent_core.services.world_state",
    ]
    for module in modules:
        proc = _probe_import(module)
        assert proc.returncode == 0, (module, proc.stderr)
        assert proc.stdout.strip() == "", (module, proc.stdout)
        assert "Runtime console initialized" not in proc.stdout
