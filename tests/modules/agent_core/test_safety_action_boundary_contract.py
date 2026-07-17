from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionPriority, ActionRequest
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.tool_execution_arbiter import ToolExecutionArbiter


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


def test_safety_action_boundary_markers_present():
    import modules.agent_core.services.action_arbiter as action_arbiter
    import modules.agent_core.services.safety_filter as safety_filter
    import modules.agent_core.services.tool_execution_arbiter as tool_execution_arbiter
    import modules.agent_core.services.tools as tools

    assert action_arbiter.SAFETY_ACTION_COMPATIBILITY is True
    assert safety_filter.SAFETY_ACTION_COMPATIBILITY is True
    assert tool_execution_arbiter.SAFETY_ACTION_COMPATIBILITY is True
    assert tools.SAFETY_ACTION_COMPATIBILITY is True

    assert action_arbiter.SAFETY_ACTION_BOUNDARY_ROLE == "agent_core_compat_action_arbiter"
    assert safety_filter.SAFETY_ACTION_BOUNDARY_ROLE == "agent_core_compat_argument_safety_filter"
    assert tool_execution_arbiter.SAFETY_ACTION_BOUNDARY_ROLE == "agent_core_compat_tool_execution_arbiter"
    assert tools.SAFETY_ACTION_BOUNDARY_ROLE == "agent_core_compat_llm_tool_registry"


def test_light_safety_action_imports_have_no_runtime_console_side_effect():
    for module in [
        "modules.agent_core.services.action_arbiter",
        "modules.agent_core.services.safety_filter",
        "modules.agent_core.services.tool_execution_arbiter",
        "modules.agent_core.services.tools",
    ]:
        proc = _probe_import(module)
        assert proc.returncode == 0, (module, proc.stderr)
        assert proc.stdout.strip() == "", (module, proc.stdout)
        assert "Runtime console initialized" not in proc.stdout


def test_action_safety_filter_contract():
    safety = ActionSafetyFilter(
        {
            "safety": {
                "min_servo_angle": 10,
                "max_servo_angle": 170,
                "max_stepper_speed": 80,
                "laser_max_duration_s": 1.5,
            }
        }
    )

    assert safety.clamp_servo(-100) == 10
    assert safety.clamp_servo(90) == 90
    assert safety.clamp_servo(999) == 170

    assert safety.clamp_stepper(120) == 80
    assert safety.clamp_stepper(-120) == -80
    assert safety.clamp_stepper(25) == 25

    assert safety.clamp_laser_duration(9.0) == 1.5
    assert safety.clamp_laser_duration(0.25) == 0.25


def test_tool_execution_arbiter_contract():
    arbiter = ToolExecutionArbiter()

    assert arbiter.can_execute("get_visual_context") is True
    assert arbiter.acquire("get_visual_context") is True
    assert arbiter.can_execute("ask_vlm_about_scene") is False
    assert arbiter.is_group_busy("vlm") is True

    status = arbiter.get_status()
    assert isinstance(status, dict)
    assert "vlm" in status
    assert status["vlm"]["tool"] == "get_visual_context"

    arbiter.release("ask_vlm_about_scene")
    assert arbiter.is_group_busy("vlm") is True

    arbiter.release("get_visual_context")
    assert arbiter.can_execute("ask_vlm_about_scene") is True

    arbiter.cancel("call-158")
    assert arbiter.can_execute("get_visual_context", call_id="call-158") is False


def test_action_request_and_action_arbiter_contract():
    handled = []

    def handler(req: ActionRequest):
        handled.append(req)
        return {"handled": req.type, "payload": dict(req.payload)}

    arbiter = ActionArbiter()
    arbiter.register_handler("speak", handler)

    req = ActionRequest(
        type="speak",
        source="agent_core",
        priority=int(ActionPriority.AGENT_TOOL),
        ttl_ms=5000,
        cooldown_key="contract:speak",
        payload={"text": "hello"},
    )

    expired_attr = getattr(req, "expired")
    expired_value = expired_attr() if callable(expired_attr) else expired_attr
    assert expired_value is False

    payload_hash_attr = getattr(req, "payload_hash")
    payload_hash_value = payload_hash_attr() if callable(payload_hash_attr) else payload_hash_attr
    assert isinstance(payload_hash_value, str)
    assert len(payload_hash_value) > 0

    result = arbiter.submit(req)
    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert result.get("action_id") == req.action_id
    assert result.get("result") == {"handled": "speak", "payload": {"text": "hello"}}
    assert handled and handled[-1] is req

    assert arbiter.cancel("missing-action-id") is True
    assert isinstance(arbiter.cancel_by_source("agent_core"), int)
    assert isinstance(arbiter.get_exclusive_status(), dict)

