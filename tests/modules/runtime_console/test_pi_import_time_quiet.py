from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from modules.runtime_console import dashboard


ROOT = Path(__file__).resolve().parents[3]


def test_startup_panel_guard_respects_safe_import_env(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_RUNTIME_CONSOLE_STARTUP_PANEL", raising=False)
    monkeypatch.setenv("SENTRYBOT_DISABLE_AUTOSTART", "true")
    assert dashboard._startup_panel_enabled() is False

    monkeypatch.setenv("SENTRYBOT_RUNTIME_CONSOLE_STARTUP_PANEL", "1")
    assert dashboard._startup_panel_enabled() is True

    monkeypatch.setenv("SENTRYBOT_RUNTIME_CONSOLE_STARTUP_PANEL", "0")
    assert dashboard._startup_panel_enabled() is False


def test_brain_import_is_quiet_under_pi_safe_import_env():
    code = "\n".join([
        "import os",
        "import sys",
        "from pathlib import Path",
        "root = Path.cwd()",
        "sys.path.insert(0, str(root))",
        "os.environ[\"SENTRYBOT_DISABLE_AUTOSTART\"] = \"true\"",
        "os.environ[\"SENTRYBOT_PI_RUNTIME_AUDIT\"] = \"1\"",
        "os.environ[\"SENTRYBOT_RUNTIME_TARGET\"] = \"pi\"",
        "import modules.autonomy.services.brain",
    ])

    env = dict(os.environ)
    env["SENTRYBOT_DISABLE_AUTOSTART"] = "true"
    env["SENTRYBOT_PI_RUNTIME_AUDIT"] = "1"
    env["SENTRYBOT_RUNTIME_TARGET"] = "pi"

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    assert "SENTRYBOT RUNTIME" not in proc.stdout
    assert "Runtime console initialized" not in proc.stdout
    assert proc.stdout.strip() == ""
