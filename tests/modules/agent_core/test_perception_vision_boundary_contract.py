from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from modules.agent_core.services.sensor_loop import SensorFeedbackLoop
from modules.agent_core.services.vision_arbiter import VisionArbiter


ROOT = Path(__file__).resolve().parents[3]


class _World:
    def __init__(self):
        self.state_updates = []
        self.scenes = []

    def update_state(self, data):
        self.state_updates.append(dict(data))

    def update_scene(self, data):
        self.scenes.append(dict(data))


class _Client:
    def __init__(self):
        self.sensors = []
        self.vision_calls = 0
        self.context_calls = 0

    def read_sensor(self, name):
        self.sensors.append(name)
        if name == "ultra_read":
            return {"cm": 42}
        if name == "imu_read":
            return {"pitch": 1.5, "roll": -2.5}
        if name == "rfid_last":
            return {"uid": "rfid-151"}
        return {}

    def get_latest_vision_results(self, limit=1):
        self.vision_calls += 1
        return [{"name": "Emir", "label": "person"}]

    def get_visual_context(self):
        self.context_calls += 1
        return {"available": True, "context": {"summary": "desk", "people": [{"name": "Emir"}]}}


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


def test_perception_vision_boundary_markers_present():
    import modules.agent_core.services.sensor_loop as sensor_loop
    import modules.agent_core.services.vision_arbiter as vision_arbiter

    assert sensor_loop.PERCEPTION_VISION_COMPATIBILITY is True
    assert vision_arbiter.PERCEPTION_VISION_COMPATIBILITY is True
    assert sensor_loop.PERCEPTION_VISION_BOUNDARY_ROLE == "agent_core_compat_sensor_loop"
    assert vision_arbiter.PERCEPTION_VISION_BOUNDARY_ROLE == "agent_core_compat_vision_arbiter"


def test_light_perception_imports_have_no_runtime_console_side_effect():
    for module in [
        "modules.agent_core.services.sensor_loop",
        "modules.agent_core.services.vision_arbiter",
    ]:
        proc = _probe_import(module)
        assert proc.returncode == 0, (module, proc.stderr)
        assert proc.stdout.strip() == "", (module, proc.stdout)
        assert "Runtime console initialized" not in proc.stdout


def test_sensor_feedback_loop_contract_for_pc_and_vision(monkeypatch):
    monkeypatch.setenv("SENTRYBOT_PC_TEST", "1")
    world = _World()
    client = _Client()
    loop = SensorFeedbackLoop(
        world,
        client=client,
        enabled=True,
        poll_hz=2.0,
        hardware_interval_s=2.0,
        vision_results_interval_s=5.0,
        visual_context_interval_s=10.0,
        skip_hardware_on_pc=True,
    )

    assert loop.pc_test is True
    assert loop._read_hardware() == {}
    assert client.sensors == []

    vision_updates = loop._read_vision_results()
    assert vision_updates["person_detected"] is True
    assert vision_updates["person_name"] == "Emir"

    loop._read_visual_context()
    assert world.scenes
    assert world.scenes[-1]["context"]["summary"] == "desk"


def test_sensor_feedback_loop_contract_for_hardware_when_not_pc(monkeypatch):
    monkeypatch.delenv("SENTRYBOT_PC_TEST", raising=False)
    monkeypatch.delenv("SENTRYBOT_PROFILE", raising=False)

    world = _World()
    client = _Client()
    loop = SensorFeedbackLoop(world, client=client, skip_hardware_on_pc=True)

    updates = loop._read_hardware()
    assert client.sensors == ["ultra_read", "imu_read", "rfid_last"]
    assert updates["distance_front_cm"] == 42.0
    assert updates["imu_pitch"] == 1.5
    assert updates["imu_roll"] == -2.5
    assert updates["last_rfid"] == "rfid-151"


def test_vision_arbiter_contract():
    arbiter = VisionArbiter()

    initial = arbiter.status()
    assert isinstance(initial, dict)

    assert arbiter.acquire("owner-a", ttl_s=30.0) is True
    after_a = arbiter.status()
    assert isinstance(after_a, dict)

    if "active_by" in after_a:
        assert after_a["active_by"] == "owner-a"
    if "busy" in after_a:
        assert after_a["busy"] is True
    if "active" in after_a:
        assert after_a["active"] is True

    assert arbiter.acquire("owner-b", ttl_s=30.0) is False
    after_b_attempt = arbiter.status()
    assert isinstance(after_b_attempt, dict)
    if "active_by" in after_b_attempt:
        assert after_b_attempt["active_by"] == "owner-a"

    arbiter.release("owner-b")
    after_wrong_release = arbiter.status()
    assert isinstance(after_wrong_release, dict)
    if "active_by" in after_wrong_release:
        assert after_wrong_release["active_by"] == "owner-a"

    arbiter.release("owner-a")
    after_release = arbiter.status()
    assert isinstance(after_release, dict)
    if "active_by" in after_release:
        assert after_release["active_by"] in {"", None}
    if "busy" in after_release:
        assert after_release["busy"] is False
    if "active" in after_release:
        assert after_release["active"] is False

    assert arbiter.acquire("owner-b", ttl_s=30.0) is True
    after_b = arbiter.status()
    assert isinstance(after_b, dict)
    if "active_by" in after_b:
        assert after_b["active_by"] == "owner-b"

