import threading
import time
from unittest.mock import patch, Mock


def test_action_arbiter_suppresses_duplicate_actions():
    from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest

    arbiter = ActionArbiter(dedup_window_s=5.0)
    first = arbiter.submit(ActionRequest(type="head_move", source="agent_core", payload={"pan": 95, "tilt": 92}))
    second = arbiter.submit(ActionRequest(type="head_move", source="agent_core", payload={"pan": 95, "tilt": 92}))

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "duplicate"


def test_speech_arbiter_prevents_overlapping_tts():
    from modules.agent_core.services.speech_arbiter import SpeechArbiter, SpeechPriority

    lock = threading.Lock()
    active = {"count": 0, "max": 0}

    def fake_speak(text, **_kwargs):
        with lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.05)
        with lock:
            active["count"] -= 1

    arbiter = SpeechArbiter(speak_fn=fake_speak)
    arbiter.start()
    try:
        arbiter.enqueue("ilk", priority=SpeechPriority.PROGRESS)
        arbiter.enqueue("ikinci", priority=SpeechPriority.FINAL_RESPONSE)
        time.sleep(0.25)
    finally:
        arbiter.stop()

    assert active["max"] == 1


def test_progress_ack_before_tool_messages():
    from modules.agent_core.services.progress import ProgressManager

    spoken = []

    class _SpeechStub:
        def enqueue_progress(self, text, cancel_token="", language=""):
            spoken.append((text, cancel_token))

        def cancel_by_token(self, _token):
            return 0

    pm = ProgressManager(speech_arbiter=_SpeechStub())
    token = pm.new_request(language="tr")
    pm.emit_ack(token, custom_text="Tamam, bakıyorum.")
    pm.emit_tool_done(token, "get_visual_context", "No visual context available yet.")
    pm.emit_tool_done(
        token,
        "get_visual_context",
        "Scene: lab | People: Emir | Importance: 0.8",
    )

    assert spoken
    assert spoken[0][0] == "Tamam, bakıyorum."
    assert not any("kameradan" in s[0].lower() for s in spoken)
    assert any("Görüntüyü aldım" in s[0] for s in spoken)


def test_final_cancels_stale_progress():
    from modules.agent_core.services.progress import ProgressManager

    cancelled = {"count": 0}

    class _SpeechStub:
        def enqueue_progress(self, text, cancel_token="", language=""):
            return "queued"

        def cancel_by_token(self, _token):
            cancelled["count"] += 1
            return 1

    pm = ProgressManager(speech_arbiter=_SpeechStub())
    token = pm.new_request(language="tr")
    pm.emit_tool_done(token, "get_vision", "Vision results unavailable.")
    pm.emit_final(token)

    assert cancelled["count"] >= 1


def test_vlm_timeout_returns_cached_context_phrase():
    from modules.agent_core.services.tools import ToolRegistry
    from modules.agent_core.services.world_state import WorldState
    from modules.agent_core.services.slam import TopologicalMap
    from modules.agent_core.services.memory import EpisodicMemory
    from modules.agent_core.services.safety_filter import ActionSafetyFilter

    mem = EpisodicMemory(db_path=":memory:")
    slam = TopologicalMap.__new__(TopologicalMap)
    slam.map_file = "test_map_registry.json"
    slam.nodes = {}
    slam.aliases = {}
    slam.current_location = "base"
    ws = WorldState()
    sf = ActionSafetyFilter()
    tr = ToolRegistry(None, mem, slam, ws, sf)

    with patch("requests.post", side_effect=TimeoutError("timeout")):
        ctx_resp = Mock()
        ctx_resp.status_code = 200
        ctx_resp.json.return_value = {
            "available": True,
            "context": {"summary": "önümde bir kişi var"}
        }
        with patch("requests.get", return_value=ctx_resp):
            out = tr.ask_vlm_about_scene("çevrede kim var")
    assert "Görüntü işleme gecikti; elimdeki son görüntüye göre" in out
