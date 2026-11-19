"""Unit & safety contract tests for extended robot hardware, OCR/face, and headless web tools."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.agent_handlers import register_default_action_handlers
from modules.agent_core.services.expression_arbiter import ExpressionArbiter
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.tools import ToolRegistry
from modules.agent_core.services.tools.tool_schemas import get_all_tool_definitions
from modules.agent_core.services.world_state import WorldState
from modules.arduino_serial.contract import validate_arduino_payload
from modules.common.web_extractor import (
    extract_readable_text,
    fetch_url_text,
    search_web_headless,
    validate_public_url,
)


def _make_orchestrator_with_handlers():
    orch = SimpleNamespace()
    orch.safety_filter = ActionSafetyFilter({"safety": {"max_stepper_speed": 80, "laser_max_duration_s": 1.5}})
    orch.action_arbiter = ActionArbiter(safety_filter=orch.safety_filter)
    orch.expression_arbiter = ExpressionArbiter()
    orch.speech_arbiter = MagicMock()
    orch._gateway_base_url = "http://127.0.0.1:8080"
    orch._action_http_timeout_s = 1.0
    orch.arduino_calls = []
    orch.ear_calls = []

    cli = MagicMock()
    cli.arduino_request.side_effect = lambda payload, timeout=1.0: orch.arduino_calls.append(payload) or {"ok": True}
    cli.set_ears.side_effect = lambda l, r: orch.ear_calls.append(("set", l, r)) or {"ok": True}
    cli.ear_gesture.side_effect = lambda g: orch.ear_calls.append(("gesture", g)) or {"ok": True}
    cli.ear_reflex.side_effect = lambda a, energy=1.0: orch.ear_calls.append(("reflex", a, energy)) or {"ok": True}
    orch.autonomy_client = cli
    register_default_action_handlers(orch)
    return orch


def test_extended_hardware_tools_route_through_arbiter_with_valid_contracts():
    orch = _make_orchestrator_with_handlers()
    reg = ToolRegistry(
        orch.autonomy_client,
        EpisodicMemory(":memory:"),
        TopologicalMap.__new__(TopologicalMap),
        WorldState(),
        orch.safety_filter,
        action_arbiter=orch.action_arbiter,
        expression_arbiter=orch.expression_arbiter,
    )
    try:
        names = [d["function"]["name"] for d in get_all_tool_definitions()]
        for expected in (
            "robot_posture",
            "move_body",
            "control_laser",
            "move_ears",
            "play_buzzer",
            "read_text_ocr",
            "register_face",
            "web_search",
            "fetch_webpage",
        ):
            assert expected in names
            assert expected in reg.tools

        assert "Action queued" in reg.execute("robot_posture", {"posture": "stand"})
        assert "Action queued" in reg.execute("move_body", {"direction": "forward", "speed": 250})
        assert "Action queued" in reg.execute("control_laser", {"state": "on", "target": "both", "duration_s": 5.0})
        assert "Action queued" in reg.execute("play_buzzer", {"cute_sound": "happy"})
        assert "Action queued" in reg.execute("move_ears", {"gesture": "wakeword"})
        assert "Action queued" in reg.execute("move_ears", {"left": 220, "right": -10})

        # Every Arduino payload queued must pass contract validation & safety clamping
        assert len(orch.arduino_calls) == 4
        for payload in orch.arduino_calls:
            assert validate_arduino_payload(payload) is None
        assert orch.arduino_calls[0] == {"cmd": "stand"}
        assert orch.arduino_calls[1] == {"cmd": "drive", "value": 80}  # clamped to max_stepper_speed=80
        assert orch.arduino_calls[2] == {"cmd": "laser", "on": True, "both": True}
        assert orch.arduino_calls[3] == {"cmd": "cute", "name": "happy"}

        assert ("gesture", "wakeword") in orch.ear_calls
        assert ("set", 180, 0) in orch.ear_calls
        reflex_res = orch.action_arbiter.submit(
            ActionRequest(type="piservo_reflex", source="autonomy", priority=90, payload={"angle": 45.0, "energy": 1.0})
        )
        assert reflex_res["ok"] is True
        assert ("reflex", 45.0, 1.0) in orch.ear_calls
    finally:
        reg.close()


def test_ocr_and_register_face_tools(monkeypatch):
    reg = ToolRegistry(
        MagicMock(),
        EpisodicMemory(":memory:"),
        TopologicalMap.__new__(TopologicalMap),
        WorldState(),
        ActionSafetyFilter(),
    )
    try:
        monkeypatch.setattr(reg, "_vision_input_available", lambda: True)
        post_mock = MagicMock()
        post_mock.side_effect = [
            SimpleNamespace(status_code=200, json=lambda: {"text": "APERTURE LABS"}),
            SimpleNamespace(status_code=200, json=lambda: {"status": "success", "message": "Registered face for Emir"}),
        ]
        monkeypatch.setattr(reg._http, "post", post_mock)

        ocr_res = reg.execute("read_text_ocr", {})
        assert "APERTURE LABS" in ocr_res
        face_res = reg.execute("register_face", {"name": "Emir"})
        assert "Registered face for Emir" in face_res
    finally:
        reg.close()


def test_web_ssrf_guard_and_headless_search_and_extract(monkeypatch):
    for bad in (
        "http://127.0.0.1:8080/arduino",
        "http://localhost:11434/api/chat",
        "http://192.168.1.50/admin",
        "http://whoismrsentry.local:11434",
        "file:///etc/passwd",
    ):
        ok, _ = validate_public_url(bad, resolve_dns=False)
        assert not ok, f"Expected SSRF block for {bad}"

    sample_wiki = """
    <html><body>
      <nav>Site Nav</nav>
      <div id="mw-content-text">
        <h1>GLaDOS</h1>
        <p>Genetic Lifeform and Disk Operating System controls Aperture Science.</p>
        <h2>Gallery</h2>
        <p>Irrelevant image gallery caption.</p>
      </div>
      <script>alert("xss")</script>
    </body></html>
    """
    extracted = extract_readable_text(sample_wiki, strip_mediawiki_noise=True)
    assert "Genetic Lifeform and Disk Operating System" in extracted
    assert "alert" not in extracted
    assert "Irrelevant image gallery" not in extracted

    # Test DDG HTML search fallback without browser
    ddg_html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="https://theportalwiki.com/wiki/GLaDOS">GLaDOS - Portal Wiki</a>
        <a class="result__snippet">AI overseer of Aperture Science.</a>
      </div>
    </body></html>
    """
    monkeypatch.setattr("modules.common.web_extractor._search_ddgs_pkg", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "requests.post",
        lambda *_a, **_k: SimpleNamespace(status_code=200, text=ddg_html),
    )
    res = search_web_headless("GLaDOS", max_results=3)
    assert res["ok"] is True
    assert res["results"][0]["title"] == "GLaDOS - Portal Wiki"
    assert res["results"][0]["url"] == "https://theportalwiki.com/wiki/GLaDOS"

    # Test fetch_webpage blocks private URLs immediately before hitting requests.get
    blocked_fetch = fetch_url_text("http://127.0.0.1:8080/healthz", resolve_dns=False)
    assert blocked_fetch["ok"] is False
