"""Regression tests for runtime log errors and warnings captured from VM/Windows runs."""
from __future__ import annotations

import asyncio
import logging
import time
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


def test_env_ollama_base_url_overrides_yaml_across_loaders(tmp_path, monkeypatch):
    from modules.agent_core import config_loader as agent_core_cfg_loader
    from modules.common.config_loader import load_agent_config, load_ai_provider_config
    from modules.common.model_policy import ModelPolicy
    from modules.common.ollama_url import resolve_env_ollama_base_url

    assert resolve_env_ollama_base_url({"SENTRYBOT_OLLAMA_BASE_URL": "http://127.0.0.1:8080/ollama"}) == ""
    assert resolve_env_ollama_base_url({"SENTRYBOT_OLLAMA_BASE_URL": "http://127.0.0.1:21434/"}) == "http://127.0.0.1:21434"

    cfg_file = tmp_path / "agent.yaml"
    cfg_file.write_text(
        """
agent:
  model: qwen3.5:9b
  ollama_base_url: http://whoismrsentry.local:11434
llm:
  provider: ollama
  model: qwen3.5:9b
  single_model_mode: true
ollama:
  base_url: http://whoismrsentry.local:11434
  model: qwen3.5:9b
ollama_service:
  server:
    host: 127.0.0.1
    port: 8099
vlm_bridge:
  vision_llm:
    enabled: true
    provider: ollama
    base_url: http://whoismrsentry.local:11434
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("SENTRYBOT_OLLAMA_BASE_URL", "http://127.0.0.1:21434")
    root_cfg = load_agent_config(str(cfg_file))
    assert root_cfg["ollama"]["base_url"] == "http://127.0.0.1:21434"
    assert root_cfg["agent"]["ollama_base_url"] == "http://127.0.0.1:21434"

    ai_cfg = load_ai_provider_config(str(cfg_file))
    assert ai_cfg["ollama"]["base_url"] == "http://127.0.0.1:21434"

    agent_cfg = agent_core_cfg_loader.load_config(str(cfg_file))
    assert agent_cfg["ollama"]["base_url"] == "http://127.0.0.1:21434"
    assert agent_cfg["agent"]["ollama_base_url"] == "http://127.0.0.1:21434"

    policy_cfg = ModelPolicy().get_provider_config(
        {"agent": {"ollama_base_url": "http://whoismrsentry.local:11434"}, "ollama": {"base_url": "http://whoismrsentry.local:11434"}}
    )
    assert policy_cfg["base_url"] == "http://127.0.0.1:21434"


def test_agent_step_handles_ollama_connect_error_without_500(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.agent_core.api.core import get_core_router
    from modules.agent_core.services.agent import AgentOrchestrator
    from modules.autonomy.services.brain_parts.vocal import VocalMixin

    ag = AgentOrchestrator(config={"llm": {"enabled": False}})
    chat_calls = []

    def _failing_chat(**_kw):
        chat_calls.append(1)
        raise httpx.ConnectError("[Errno -2] Name or service not known")

    ag.ollama_client = SimpleNamespace(chat=_failing_chat)
    ag.cooldown = 0.0
    ag.speech_arbiter._speak_fn = None

    app = FastAPI()
    app.include_router(get_core_router(ag))
    tc = TestClient(app)

    r1 = tc.post("/step", json={"query": "Kendini tanit", "language": "tr"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is False
    assert d1["error"] == "ollama_unavailable"
    assert len(chat_calls) == 1

    # Second call uses 5s negative cache without retrying dead host
    r2 = tc.post("/step", json={"query": "Tekrar dene", "language": "tr"})
    assert r2.status_code == 200
    assert r2.json()["error"] == "ollama_unavailable"
    assert len(chat_calls) == 1

    # Background step_event stays silent on text
    r_evt = tc.post("/step_event", json={"event_type": "sound_detected", "event_prompt": "ses"})
    assert r_evt.status_code == 200
    assert r_evt.json()["ok"] is False
    assert r_evt.json()["text"] == ""

    # VocalMixin treats ok=False agent response as unhandled so it doesn't TTS-speak error text
    spoken = []

    class _VocalHarness(VocalMixin):
        agent = ag
        state = {}
        memory = SimpleNamespace(add_event=lambda *_a: None)
        mood = SimpleNamespace(get_dominant_emotion=lambda: "neutral")
        client = SimpleNamespace(speak_preferred=lambda *a, **k: spoken.append(a))

        @staticmethod
        def _enrich_user_text_with_companion_context(text, speaker=None):
            return text

        @staticmethod
        def _is_active_request(_rid):
            return True

        @staticmethod
        def _remember_person_chat(*_a, **_k):
            pass

    vh = _VocalHarness()
    assert vh._try_agent_core_path("merhaba", "tr", None, "req1") is False
    assert spoken == []


def test_speech_final_dedup_with_ts_and_stale_sound_direction(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.autonomy.api.router import get_router as get_autonomy_router
    from modules.autonomy.services.brain import AutonomyBrain

    brain = AutonomyBrain(
        {
            "llm": {"enabled": False},
            "owner_learning": {"profile_path": str(tmp_path / "owners.json")},
            "safe_navigation": {"places_path": str(tmp_path / "safe.json")},
            "topomap_motion": {"map_path": str(tmp_path / "topo.json")},
            "shadow_learner": {"save_path": str(tmp_path / "macros.yml")},
            "world_memory": {"db_path": str(tmp_path / "wm.db")},
        }
    )
    try:
        heard: list[str] = []
        brain._dispatch_final_speech = lambda text, **_kw: heard.append(text)

        app = FastAPI()
        app.include_router(get_autonomy_router(brain))
        tc = TestClient(app)

        # 1. Push via POST /autonomy/speech with ts=100.5, then poll same ts -> fires ONCE
        resp = tc.post("/autonomy/speech", json={"text": "Hey Minecraft", "language": "tr", "final": True, "ts": 100.5})
        assert resp.status_code == 200
        brain.state["last_speech_time"] = 0.0  # Simulate >2.0s elapsed before poll arrives
        brain.client = SimpleNamespace(get_last_speech=lambda: {"text": "Hey Minecraft", "language": "tr", "final": True, "ts": 100.5})
        brain._sense_speech_text()
        assert heard == ["Hey Minecraft"]

        # 2. Legacy push without ts followed by poll carrying ts within debounce latches ts
        brain.on_speech_final("Selam", source_lang="tr", ts=0.0)
        brain.on_speech_final("Selam", source_lang="tr", ts=200.25)
        brain.state["last_speech_time"] = 0.0  # Even after window expires, same ts=200.25 stays deduped
        brain.on_speech_final("Selam", source_lang="tr", ts=200.25)
        assert heard == ["Hey Minecraft", "Selam"]

        # 3. Stale sound direction does not re-trigger every 15s, and skips step_event when ollama is offline
        sound_events = []
        brain.agent = SimpleNamespace(step_event=lambda *a, **k: sound_events.append(a))
        brain.config["llm"] = {"enabled": True}
        brain.client = SimpleNamespace(
            get_speech_direction=lambda: {"ok": True, "angle": 0.0, "ts": 50.0, "fresh": True},
            is_service_available=lambda svc: False,
            queue_action=lambda *a, **k: {"ok": True},
            push_interaction_event=lambda *a, **k: {"ok": True},
        )
        brain._react_to_sound = lambda angle: sound_events.append(("react", angle))
        brain._sense_sound_direction()
        brain.state["last_sound_time"] = 0.0
        brain._sense_sound_direction()  # Same ts=50.0 -> skipped
        brain.client.get_speech_direction = lambda: {"ok": True, "angle": 0.0, "ts": 80.0, "fresh": False}
        brain._sense_sound_direction()  # Stale fresh=False -> skipped
        assert len(sound_events) == 1
    finally:
        brain.stop()


def test_logwrapper_quiets_httpcore_and_urllib3_connectionpool(tmp_path, monkeypatch):
    from modules.runtime_console.logwrapper import xLogService as service

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_memory = service._MEMORY_HANDLER
    root.handlers.clear()
    service._MEMORY_HANDLER = None
    monkeypatch.chdir(tmp_path)
    try:
        service.init_logging({"enable_console": False, "enable_file": False})
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("httpcore.http11").getEffectiveLevel() == logging.WARNING
        assert logging.getLogger("urllib3.connectionpool").level == logging.WARNING
    finally:
        for handler in logging.getLogger().handlers:
            handler.close()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        service._MEMORY_HANDLER = original_memory


def test_speak_say_stream_recovers_after_wakeword_stop(monkeypatch):
    import numpy as np
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.voice.speak.api.router import get_router
    from modules.voice.speak.services import player as player_mod
    from modules.voice.speak.services.pcm import PCM
    from modules.voice.speak.xSpeakService import SpeakService

    played: list[int] = []

    class _FakeSD:
        @staticmethod
        def play(data, **_kwargs):
            played.append(len(data))

        @staticmethod
        def stop():
            return None

    monkeypatch.setenv("SENTRYBOT_ALLOW_TEST_TTS", "1")
    monkeypatch.setattr(player_mod, "sd", _FakeSD)

    svc = SpeakService()
    svc.tts = SimpleNamespace(
        synthesize=lambda text, overrides=None: PCM(
            data=np.zeros(220, dtype=np.float32),
            samplerate=22050,
            channels=1,
        ),
        health=lambda: {"available": True, "engine": "piper"},
    )

    # Simulate wakeword barge-in BEFORE any playback: sets both instance and module _play_stop
    svc.stop()
    assert svc.player.is_stopped is True

    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    resp = client.post(
        "/speak/say_stream",
        json={"text": "Birinci cumle burada! Ikinci cumle de burada!", "max_chunk_chars": 40},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    deadline = time.monotonic() + 3.0
    job = None
    while time.monotonic() < deadline:
        job = client.get(f"/speak/jobs/{job_id}").json()["job"]
        if job and job["status"] in {"done", "failed", "interrupted"}:
            break
        time.sleep(0.02)

    assert job is not None
    assert job["status"] == "done"
    assert job["done_chunks"] == 2
    assert len(played) == 2

    # Clean module-global stop event after test
    svc.player.clear_stop()


def test_memory_consolidator_extract_facts_llm_no_kind_keyerror():
    from modules.agent_core.services.memory_consolidator import MemoryConsolidator

    seen_prompts: list[str] = []

    class _FakeLLM:
        model = "qwen3.5:9b"

        def chat(self, model, messages, options=None):
            seen_prompts.append(messages[0]["content"])
            return {
                "message": {
                    "content": '[{"kind": "people", "name": "Emir", "summary": "User name is Emir", "confidence": 0.9}]'
                }
            }

    mc = MemoryConsolidator(llm_client=_FakeLLM())
    facts = mc.extract_facts_llm("User: benim adim Emir {test} | Bot: Merhaba", speaker="Emir")
    assert len(facts) == 1
    assert facts[0]["kind"] == "people"
    assert facts[0]["name"] == "Emir"
    assert "{test}" in seen_prompts[0]


def test_sound_detected_skips_llm_during_speech_and_boredom_suppresses_ack(tmp_path):
    from modules.agent_core.services.agent import AgentOrchestrator
    from modules.autonomy.services.brain import AutonomyBrain

    brain = AutonomyBrain(
        {
            "llm": {"enabled": True},
            "defaults": {"boredom_threshold_s": 0.01},
            "owner_learning": {"profile_path": str(tmp_path / "owners.json")},
            "safe_navigation": {"places_path": str(tmp_path / "safe.json")},
            "topomap_motion": {"map_path": str(tmp_path / "topo.json")},
            "shadow_learner": {"save_path": str(tmp_path / "macros.yml")},
            "world_memory": {"db_path": str(tmp_path / "wm.db")},
        }
    )
    try:
        actions: list[str] = []
        sound_steps: list[str] = []
        brain.agent = SimpleNamespace(
            is_busy=False,
            step_event=lambda evt, prompt, **_kw: sound_steps.append(evt),
            speech_arbiter=SimpleNamespace(is_speaking=lambda: False),
        )
        brain.client = MagicMock()
        brain.client.is_service_available.return_value = True
        brain.client.queue_action.side_effect = lambda action_type, **_kw: actions.append(action_type) or {"ok": True}
        brain.client.push_interaction_event.return_value = {"ok": True}
        brain.client.is_wakeword_window_active.return_value = True
        brain.client.get_operational_mode.return_value = "active"
        brain.client.get_vision_context.return_value = None
        brain.client.get_vision_results.return_value = []
        brain.client.check_rfid.return_value = False

        # Wakeword window active -> physical reflex runs, heavy sound_detected LLM step is skipped
        brain.state["last_sound_reaction_time"] = 0.0
        brain._react_to_sound(10.0)
        assert "piservo_reflex" in actions
        assert sound_steps == []

        # While _speech_busy is True, _think() must not flip is_bored=True right after a turn
        brain.state["last_interaction"] = 0.0
        brain._speech_busy = True
        brain._think()
        assert brain.state["is_bored"] is False
        brain._speech_busy = False

        # Boredom agentic step on real AgentOrchestrator must suppress spoken Laya ack fillers
        ag = AgentOrchestrator(config={"llm": {"enabled": False}, "agent": {"cooldown_s": 0.0}})
        ag.ollama_client = SimpleNamespace(chat=lambda **_k: {"message": {"content": "Sessiz gozlem."}})
        ag._probe_ollama_connectivity = lambda: None
        ag.speech_arbiter._speak_fn = lambda **_k: {"ok": True}
        ack_calls: list[bool] = []
        orig_emit_ack = ag.progress_manager.emit_ack

        def _capture_ack(token, custom_text="", *, speak=True):
            ack_calls.append(bool(speak))
            return orig_emit_ack(token, custom_text=custom_text, speak=speak)

        ag.progress_manager.emit_ack = _capture_ack
        brain.agent = ag
        brain.behavior_composer = None
        brain._make_agentic_decision(reason="boredom", context_note="unit test")
        assert ack_calls and all(s is False for s in ack_calls)

        # Regular foreground user step retains spoken ack behavior when not fast-path
        ack_calls.clear()
        ag.step("Bu cok uzun ve kapsamli bir arastirma gorevi niteliginde kullanici istegidir " * 3, language="tr")
        assert ack_calls == [True]
    finally:
        brain.stop()
