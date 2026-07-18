from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from modules.agent_core.services.expression_arbiter import ExpressionArbiter
from modules.agent_core.services.idle_behavior import IdleBehaviorSystem


ROOT = Path(__file__).resolve().parents[3]


class _Agent:
    def __init__(self) -> None:
        self.is_busy = False


class _Client:
    def __init__(self) -> None:
        self.neopixel_calls = []

    def set_neopixel(self, *args, **kwargs):
        self.neopixel_calls.append((args, kwargs))
        return {"ok": True}


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


def test_expression_idle_boundary_markers_present():
    import modules.agent_core.services.expression_arbiter as expression_arbiter
    import modules.agent_core.services.idle_behavior as idle_behavior

    assert expression_arbiter.EXPRESSION_IDLE_COMPATIBILITY is True
    assert idle_behavior.EXPRESSION_IDLE_COMPATIBILITY is True
    assert expression_arbiter.EXPRESSION_IDLE_BOUNDARY_ROLE == "agent_core_compat_expression_arbiter"
    assert idle_behavior.EXPRESSION_IDLE_BOUNDARY_ROLE == "agent_core_compat_idle_heartbeat"


def test_light_expression_idle_imports_have_no_runtime_console_side_effect():
    for module in [
        "modules.agent_core.services.expression_arbiter",
        "modules.agent_core.services.idle_behavior",
    ]:
        proc = _probe_import(module)
        assert proc.returncode == 0, (module, proc.stderr)
        assert proc.stdout.strip() == "", (module, proc.stdout)
        assert "Runtime console initialized" not in proc.stdout


def test_expression_arbiter_contract():
    arbiter = ExpressionArbiter()

    assert arbiter.status() == {"lights_owner": "", "oled_owner": ""}

    assert arbiter.claim_lights("owner-a") is True
    assert arbiter.claim_lights("owner-b") is False
    assert arbiter.claim_lights("owner-b", force=True) is True
    assert arbiter.status()["lights_owner"] == "owner-b"

    assert arbiter.claim_oled("oled-a") is True
    assert arbiter.claim_oled("oled-b") is False
    assert arbiter.claim_oled("oled-b", force=True) is True
    assert arbiter.status()["oled_owner"] == "oled-b"

    arbiter.release("owner-a")
    assert arbiter.status()["lights_owner"] == "owner-b"
    assert arbiter.status()["oled_owner"] == "oled-b"

    arbiter.release("owner-b")
    assert arbiter.status()["lights_owner"] == ""
    assert arbiter.status()["oled_owner"] == "oled-b"

    arbiter.release("oled-b")
    assert arbiter.status() == {"lights_owner": "", "oled_owner": ""}


def test_idle_behavior_system_contract_start_stop_without_semantic_idle_decision():
    agent = _Agent()
    client = _Client()
    idle = IdleBehaviorSystem(agent, client=client)

    assert idle.agent is agent
    assert idle.client is client
    assert idle.running is False
    assert idle.thread is None

    idle.start()
    try:
        assert idle.running is True
        assert idle.thread is not None
        assert idle.thread.daemon is True
    finally:
        idle.stop()

    assert idle.running is False
    # The heartbeat loop is time-gated at about 15s. Contract test must not force a semantic idle action.
    time.sleep(0.02)
    assert isinstance(client.neopixel_calls, list)
