"""Regression tests for runtime log errors and warnings captured from VM/Windows runs."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from modules.autonomy.services.behavior_planner import BehaviorPlanner
from modules.autonomy.services.brain import AutonomyBrain
from modules.autonomy.services.client import ServiceClient
from modules.autonomy.services.reflection_planner import ReflectionPlanner
from modules.camera.device_manager import CameraDeviceManager, CameraMode
from modules.common.ollama_compat import call_ollama_chat, chat_accepts_kwarg
from modules.gateway.xGatewayService import _shutdown_started_services
from modules.visual_output.oled_faces.config_loader import load_config as load_oled_cfg
from modules.visual_output.oled_faces.services.mapper import FaceMapper
from modules.vlm_bridge.services.processor import VisionProcessor
from modules.voice.audio_router import AudioCapture, AudioConfig, AudioRouter, AudioRouterConfig, _portaudio_device


class _OldOllamaClient:
    """Mimics ollama<0.5 Client.chat signature (no `think` or `priority` kwargs)."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def chat(
        self,
        model: str = "",
        messages=None,
        *,
        tools=None,
        stream: bool = False,
        format=None,
        options=None,
        keep_alive=None,
    ):
        self.calls.append({"model": model, "messages": messages, "tools": tools, "stream": stream})
        return self.payload


class _DynamicRejectingClient:
    """Mimics a wrapper accepting **kwargs at Python level that rejects `think` at runtime."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.seen_kwargs = []

    def chat(self, **kwargs):
        self.seen_kwargs.append(dict(kwargs))
        if "think" in kwargs:
            raise TypeError("Client.chat() got an unexpected keyword argument 'think'")
        return self.payload


def test_ollama_compat_drops_unsupported_think_and_priority(monkeypatch, tmp_path):
    old_cli = _OldOllamaClient({"message": {"content": "{}"}})
    assert chat_accepts_kwarg(old_cli, "think") is False
    assert chat_accepts_kwarg(old_cli, "priority") is False
    res = call_ollama_chat(old_cli, model="qwen3.5:9b", messages=[{"role": "user", "content": "hi"}], think=False, priority=0)
    assert res == {"message": {"content": "{}"}}
    assert len(old_cli.calls) == 1

    dyn_cli = _DynamicRejectingClient({"message": {"content": "ok"}})
    res2 = call_ollama_chat(dyn_cli, model="qwen3.5:9b", messages=[], think=False, priority=1)
    assert res2 == {"message": {"content": "ok"}}
    assert len(dyn_cli.seen_kwargs) == 2
    assert "think" not in dyn_cli.seen_kwargs[-1]

    # Exercise BehaviorPlanner & ReflectionPlanner against old Ollama client signature
    monkeypatch.setattr(
        "modules.autonomy.services.behavior_planner.ollama",
        SimpleNamespace(Client=lambda host=None: _OldOllamaClient({"message": {"content": "[]"}})),
    )
    planner = BehaviorPlanner({"llm_planning_enabled": True, "world_memory": {"db_path": str(tmp_path / "bp.db")}})
    plan = planner.generate_plan({}, "empty room", [])
    assert isinstance(plan, list)

    monkeypatch.setattr(
        "modules.autonomy.services.reflection_planner.ollama",
        SimpleNamespace(Client=lambda host=None: _OldOllamaClient({"message": {"content": '{"summary": "saved"}'}})),
    )
    refl = ReflectionPlanner({"llm_planning_enabled": True})
    out = refl.reflect({"actions": []}, {"reason": "done"}, {}, "clear")
    assert out is not None and out["summary"] == "saved"

    # Exercise AgentTurnMixin._chat_turn with old-signature client + ollama_think=False
    from modules.agent_core.services.agent_turn import AgentTurnMixin

    class _TurnHarness(AgentTurnMixin):
        llm_provider = "ollama"
        provider_client = None
        ollama_client = _OldOllamaClient({"message": {"content": "merhaba"}})
        clm_fallback_enabled = False
        clm_fallback_model = ""
        fallback_on_error = False
        fallback_on_missing_model = False
        ollama_think = False
        ollama_keep_alive = -1
        model = "qwen3.5:9b"

        @staticmethod
        def _pick_runtime_model(m):
            return m

    turn = _TurnHarness()
    reply = turn._chat_turn("qwen3.5:9b", [{"role": "user", "content": "selam"}], None, None)
    assert reply == {"message": {"content": "merhaba"}}


def test_service_client_update_emotions_and_real_autonomy_sync(tmp_path):
    posts = []
    gets = []

    class _FakeResp:
        def __init__(self, status_code: int, payload=None):
            self.status_code = status_code
            self._payload = payload if payload is not None else {"ok": True}

        def json(self):
            return self._payload

    client = ServiceClient(
        {
            "neopixel": "http://127.0.0.1:18080/neopixel",
            "interactions": "http://127.0.0.1:18080/interactions",
            "arduino": "http://127.0.0.1:18080/arduino",
            "animate": "http://127.0.0.1:18080/animate",
        }
    )
    fake_session = MagicMock()
    fake_session.post.side_effect = lambda url, **kw: (posts.append((url, kw)), _FakeResp(404 if "/arduino/" in url or "/animate/" in url else 200))[1]
    fake_session.get.side_effect = lambda url, **kw: (gets.append(url), _FakeResp(404))[1]
    client._session = fake_session

    res = client.update_emotions(["curiosity"])
    assert res == {"ok": True}
    assert any(u.endswith("/neopixel/emote") and kw.get("params", {}).get("emotion") == "curiosity" for u, kw in posts)

    # Real AutonomyBrain._sync_emotion() with REAL ServiceClient (not MagicMock)
    brain = AutonomyBrain(
        {
            "llm": {"enabled": False},
            "visual_state": {"emotion_min_interval_s": 0.0},
            "owner_learning": {"profile_path": str(tmp_path / "owners.json")},
            "safe_navigation": {"places_path": str(tmp_path / "safe.json")},
            "topomap_motion": {"map_path": str(tmp_path / "topo.json")},
            "shadow_learner": {"save_path": str(tmp_path / "macros.yml")},
            "world_memory": {"db_path": str(tmp_path / "wm.db")},
        }
    )
    try:
        brain.client = client
        brain._last_emotion_sync_ts = 0.0
        brain._last_emotion_sent = None
        brain.mood.modify("happiness", 40)
        brain._sync_emotion()
    finally:
        brain.stop()

    # Cooldown suppresses repeated 404 probes on unmounted animate/rfid endpoints
    assert client.run_animation("owner_scan") is None
    animate_count_before = sum(1 for u, _ in posts if "/animate/run" in u)
    assert client.run_animation("owner_scan") is None
    animate_count_after = sum(1 for u, _ in posts if "/animate/run" in u)
    assert animate_count_after == animate_count_before

    assert client.check_rfid("@gateway/arduino/rfid/authorize") is False
    rfid_before = len(gets)
    assert client.check_rfid("@gateway/arduino/rfid/authorize") is False
    assert len(gets) == rfid_before


def test_oled_face_mapper_cognitive_states_avoid_unknown_emotion(caplog):
    mapper = FaceMapper(load_oled_cfg())
    with caplog.at_level(logging.DEBUG, logger="common.emotion_vocab"):
        for state in ("thinking", "speaking", "listening"):
            act = mapper.from_emotions([state])
            assert act.mode == "animation"
            assert act.name in {"thinking", "listening"}
    assert not any("Unknown emotion label" in rec.message for rec in caplog.records)


def test_vlm_stream_respects_camera_healthz_ok_flag(monkeypatch):
    proc = VisionProcessor({"enabled": False})
    proc.camera_source = "http://127.0.0.1:8080/camera/video"

    monkeypatch.setattr(
        "modules.vlm_bridge.services.processor_stream.requests.get",
        lambda url, timeout=1.0: SimpleNamespace(status_code=200, json=lambda: {"ok": False, "enabled": True}),
    )
    assert proc._http_camera_ready() is False

    monkeypatch.setattr(
        "modules.vlm_bridge.services.processor_stream.requests.get",
        lambda url, timeout=1.0: SimpleNamespace(status_code=200, json=lambda: {"ok": True, "enabled": True}),
    )
    assert proc._http_camera_ready() is True


def test_audio_capture_mono_to_stereo_expansion_and_idempotent_init(caplog):
    assert _portaudio_device("default") is None
    assert _portaudio_device("none") is None
    assert _portaudio_device("3") == 3

    received = []

    class _Consumer:
        def on_audio_frame(self, frame, ts):
            received.append(frame.copy())

        def on_start(self):
            pass

        def on_stop(self):
            pass

    cap = AudioCapture(AudioConfig(channels=2, format="int16"))
    cap._active_channels = 1
    cap._running = True
    cap.register_consumer("c1", _Consumer())
    mono_samples = np.array([100, -200, 300, -400], dtype=np.int16)
    cap._enqueue_raw_chunk(mono_samples.tobytes(), 1.0)
    cap._raw_queue.put_nowait(None)
    cap._dispatch_loop()

    assert len(received) == 1
    assert received[0].shape == (4, 2)
    assert np.array_equal(received[0][:, 0], mono_samples)
    assert np.array_equal(received[0][:, 1], mono_samples)

    # Idempotent initialize while capture running must not log WARNING
    router = AudioRouter(AudioRouterConfig())
    old_cap = router._capture
    try:
        router._capture = SimpleNamespace(_running=True)
        with caplog.at_level(logging.WARNING, logger="voice.audio_router"):
            router.initialize(AudioRouterConfig())
        assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    finally:
        router._capture = old_cap


def test_idempotent_shutdown_and_camera_handle_release(caplog):
    import scripts.run_robot as run_robot

    mgr = CameraDeviceManager.get_instance()
    mgr.shutdown()
    handle = mgr.acquire("test_owner_capture", CameraMode.LOCAL)
    with caplog.at_level(logging.WARNING, logger="camera.device_manager"):
        mgr.shutdown()
        assert handle.release() is False
        mgr.shutdown()
    assert not any("non-existent reference" in rec.message for rec in caplog.records)

    calls = []

    class _Svc:
        def stop(self):
            calls.append("stop")

    svc = _Svc()
    started = {"agent": svc, "agent_core": svc, "agent_service": svc}
    asyncio.run(_shutdown_started_services(started))
    assert len(calls) == 1
    assert started["_services_stopped"] is True

    app = SimpleNamespace(state=SimpleNamespace(started=started))
    run_robot._stop_started_services(app)
    assert len(calls) == 1


def test_interactions_arduino_monitor_disabled_when_arduino_unmounted(monkeypatch):
    from fastapi import FastAPI
    from modules.gateway.services import bootstrap_ai

    monkeypatch.setattr(bootstrap_ai, "_should_autostart_services", lambda: False)
    app = FastAPI()
    started = {"gateway_base_url": "http://127.0.0.1:8080"}
    bootstrap_ai._include_interactions(app, started, {})
    eng = started["interactions"]
    assert eng.monitor_cfg.get("arduino") is None
    assert eng.get_state()["ctx"]["arduino_connected"] is False


def test_agent_turn_core_skips_ack_on_unavailable_provider_or_event(monkeypatch):
    from modules.agent_core.services.agent import AgentOrchestrator

    ag = AgentOrchestrator.__new__(AgentOrchestrator)
    ag.config = {}
    ag.world_state = SimpleNamespace(update_laya_state=lambda _d: None)
    ag.tool_registry = SimpleNamespace(status_hook=None)
    ack_calls = []
    ag.progress_manager = SimpleNamespace(
        new_request=lambda language="tr": "tok1",
        emit_ack=lambda token, custom_text="", speak=True: ack_calls.append((token, custom_text, speak)),
        emit_final=lambda token: None,
    )
    ag._try_enter_turn = lambda prompt, bypass_cooldown=False: True
    ag._bind_speaker = lambda spk: None
    ag._exit_turn = lambda: None
    ag._should_fast_path = lambda prompt, native_tools=False: False
    ag._record_laya_latency = lambda _tid: None
    ag._build_progress_callback = lambda tok, cb: (lambda _evt: None)
    ag._prepare_turn_context = lambda prompt, lang, tid: (None, "", "qwen3.5:9b")
    ag._normalize_session_language = lambda lang: lang or "tr"
    ag.speech_arbiter = SimpleNamespace(_speak_fn=None)
    ag.last_routed_subagents = []

    # 1. Unavailable provider must return error WITHOUT emitting spoken ack
    ag._check_provider_availability = lambda: {"text": "down", "error": "ollama_down"}
    res = ag._run_turn_core("merhaba", bypass_cooldown=False, language="tr", speaker=None, native_tools=False, trace_id="t1")
    assert res["error"] == "ollama_down"
    assert ack_calls == []

    # 2. Background event_type ("sound_detected") must never speak ack
    ag._check_provider_availability = lambda: None
    ag.tri_layer_enabled = False
    ag.fast_path_num_predict = None
    ag.max_steps = 1
    ag._make_sentence_callback = lambda *_a, **_k: None
    ag._native_loop_messages = lambda *_a, **_k: []
    ag._run_native_history_loop = lambda *_a, **_k: ("", 0)
    ag._finalize_turn_memory = lambda *_a, **_k: None
    ag.autonomy_client = None
    ag._run_turn_core(
        "arka plan sesi",
        bypass_cooldown=True,
        language="tr",
        speaker=None,
        native_tools=False,
        trace_id="t2",
        event_type="sound_detected",
    )
    assert ack_calls and ack_calls[-1][2] is False
