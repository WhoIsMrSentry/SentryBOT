"""Regression tests for runtime bugs identified in WSL SentryBOT logs."""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.tools import ToolRegistry
from modules.agent_core.services.world_state import WorldState
from modules.ai_provider.services.persona_rag import PersonaManager
from modules.ai_provider.services.tags import strip_speech_control_artifacts
from modules.autonomy.services.brain_parts.speech_react import SpeechReactMixin
from modules.autonomy.services.brain_parts.vocal import VocalMixin
from modules.autonomy.services.client_parts.client_speech import ClientSpeechMixin
from modules.common.translator import HybridTranslator
from modules.common.web_extractor import _simplify_search_query, search_web_headless
from modules.expression.semantic.services.adapters.head_adapter import HeadAdapter
from modules.gateway import readiness
from modules.voice.speak.api.router import get_router as get_speak_router
from modules.voice.speak.services.lcd_sync import SpeechLcdSync
from modules.voice.speak.services.pcm import PCM
from modules.voice.speak.xSpeakService import SpeakService
from modules.voice.speech.services import online_stt
from modules.voice.speech.services.audio_filters import SoftwareEchoGate, SpeechAudioFilterMixin
from modules.voice.speech.services.recognizer import Recognizer
from modules.voice.speech.services.turn_taking import DynamicTurnTakingEngine
from modules.voice.wakeword.xWakewordService import WakewordService


def _make_bare_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentOrchestrator:
    for pname, ptxt in (("sentry", "You are SentryBOT."), ("glados", "You are GLaDOS.")):
        pdir = tmp_path / pname
        (pdir / "knowledge").mkdir(parents=True)
        (pdir / "persona.txt").write_text(ptxt, encoding="utf-8")
        (pdir / "persona.yml").write_text(f"id: {pname}\ndisplay_name: {pname}\n", encoding="utf-8")

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = {
        "agent": {"model": "sentry:latest", "personalities_dir": str(tmp_path), "persona": "glados"},
        "models": {"single_model_mode": False, "roles": {"chat": "sentry:latest"}},
        "tri_layer": {"enabled": False, "persona": {"stream": True}},
        "translation": {"enabled": False},
    }
    agent.model = "sentry:latest"
    agent.max_history = 10
    agent.cooldown = 0.0
    agent.last_run = 0.0
    agent.is_busy = False
    agent.temperature = 0.1
    agent.num_ctx = 2048
    agent.chat_num_predict = 128
    agent.fast_path_enabled = False
    agent.fast_path_max_chars = 32
    agent.fast_path_num_predict = 64
    agent.fast_path_max_steps = 2
    agent.max_steps = 4
    agent.tri_layer_enabled = False
    agent.persona_stream_enabled = True
    agent.llm_provider = "ollama"
    agent.clm_fallback_enabled = False
    agent.clm_fallback_model = ""
    agent.fallback_on_missing_model = False
    agent.fallback_on_error = False
    agent.ollama_think = True
    agent.ollama_keep_alive = -1
    agent.last_routed_subagents = []
    agent.chat_history = []
    agent._turn_lock = threading.Lock()
    agent._turn_epoch_lock = threading.RLock()
    agent._history_lock = threading.RLock()
    agent._active_turn_token = ""
    agent._active_turn_cancel = None
    agent._active_turn_thread_id = None
    agent._external_persona_epoch = 0
    agent._just_cancelled_until = 0.0
    agent.world_state = WorldState()
    agent.memory = EpisodicMemory(":memory:")
    agent.memory_consolidator = MagicMock()
    agent.memory_consolidator.get_context_summary.return_value = ""
    agent.progress_manager = MagicMock()
    agent.progress_manager.new_request.return_value = "tok"
    agent.speech_arbiter = MagicMock()
    agent.speech_arbiter._speak_fn = lambda *_a, **_k: None
    agent.speech_arbiter.enqueue_final_chunk.return_value = "id1"
    agent.tool_registry = ToolRegistry(
        MagicMock(),
        agent.memory,
        TopologicalMap.__new__(TopologicalMap),
        agent.world_state,
        ActionSafetyFilter(),
    )
    agent._init_persona_runtime(agent.config)
    monkeypatch.setattr(agent, "_check_provider_availability", lambda: None)
    return agent


def test_external_persona_switch_cancels_in_flight_turn_without_history_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = _make_bare_agent(tmp_path, monkeypatch)
    entered_stream = threading.Event()
    release_stream = threading.Event()

    def _slow_chat(**_kwargs):
        def _gen():
            entered_stream.set()
            release_stream.wait(timeout=2.0)
            yield {"message": {"content": "🍰Neurotoxin reply from GLaDOS.🤞"}}

        return _gen()

    agent.ollama_client = MagicMock()
    agent.ollama_client.chat.side_effect = _slow_chat
    agent._pick_runtime_model = lambda m: m  # type: ignore[method-assign]

    results: list = []
    t = threading.Thread(target=lambda: results.append(agent.step("Neymar", language="tr", native_tools=True)))
    t.start()
    try:
        assert entered_stream.wait(timeout=2.0)
        # Simulate voice shortcut switching persona to sentry while GLaDOS turn is mid-flight
        agent.apply_persona("sentry", notify=False, trigger_emotion=False)
        release_stream.set()
        t.join(timeout=3.0)

        assert results and results[0]["cancelled"] is True
        assert agent.active_persona == "sentry"
        # Critical invariant: cancelled GLaDOS output must NOT contaminate sentry's chat_history
        assert agent.chat_history == []
        agent.speech_arbiter.interrupt_all.assert_called()
    finally:
        agent._close_persona_runtime()
        agent.tool_registry.close()


def test_vocal_skips_direct_ollama_fallback_when_agent_busy_or_cancelled() -> None:
    class _Harness(VocalMixin):
        state: dict = {}
        memory = SimpleNamespace(add_event=lambda *_a: None)
        mood = SimpleNamespace(get_dominant_emotion=lambda: "neutral")
        client = MagicMock()

        @staticmethod
        def _enrich_user_text_with_companion_context(text, speaker=None):
            return text

        @staticmethod
        def _is_active_request(_rid):
            return True

        @staticmethod
        def _remember_person_chat(*_a, **_k):
            pass

    h = _Harness()
    h.agent = SimpleNamespace(
        speech_arbiter=SimpleNamespace(_speak_fn=lambda *_a, **_k: None),
        step=lambda *_a, **_k: None,
    )
    assert h._try_agent_core_path("switch Clothes", "en", None, "req1") is True

    h.agent = SimpleNamespace(
        speech_arbiter=SimpleNamespace(_speak_fn=lambda *_a, **_k: None),
        step=lambda *_a, **_k: {"ok": False, "cancelled": True, "text": ""},
    )
    assert h._try_agent_core_path("switch Clothes", "en", None, "req2") is True
    h.client.chat.assert_not_called()


def test_echo_gate_wakeword_and_turn_taking_noise_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. SpeakService computes non-baseline int16 RMS from louder float32 PCM
    pcm = PCM(data=np.full(2205, 0.25, dtype=np.float32), samplerate=22050, channels=1)
    assert SpeakService._estimate_pcm_rms_int16(pcm) > 5000.0

    # 2. SpeechAudioFilterMixin does NOT buffer echo-suppressed PCM into _utterance_pcm
    class _FilterHarness(SpeechAudioFilterMixin):
        def __init__(self) -> None:
            self.cfg = {"direction": {"enabled": False}}
            self.capture = SimpleNamespace(cfg=SimpleNamespace(channels=1, dtype="int16"))
            self._direction = None
            self._last_angle = None
            self._last_angle_ts = 0.0
            self._last_audio_level = 0.0
            self._tracking = False
            self._pan = None
            self._stt_input_gain = 1.0
            self._auto_language = True
            self._utterance_pcm = bytearray()
            self._max_utterance_bytes = 32000
            self._echo_gate = SoftwareEchoGate(suppression_gain=0.08, barge_in_ratio=2.8, hold_time_s=0.65)
            self._echo_gate.set_tts_playback(True, estimated_rms=1500.0)

    fh = _FilterHarness()
    echo_chunk = np.full(480, 1200, dtype=np.int16).tobytes()
    out_echo = fh._condition_mono_chunk(echo_chunk, 1200.0)
    assert fh._last_frame_echo_suppressed is True
    assert float(np.max(np.abs(np.frombuffer(out_echo, dtype=np.int16)))) <= 100.0

    # 3. WakewordService drops echo frames during TTS playback but allows strong barge-in
    ww = WakewordService.__new__(WakewordService)
    ww._vad_gate_enabled = False
    ww._vad_min_rms = 75.0
    ww._vad_hangover_sec = 0.6
    ww._vad_hangover_until = 0.0
    ww._energy_gate_passed = 0
    ww._energy_gate_skipped = 0
    ww._openwakeword = SimpleNamespace(_calibration_done=True)
    ww._echo_gate = SoftwareEchoGate(suppression_gain=0.05, barge_in_ratio=3.0, hold_time_s=0.75)
    ww.set_tts_playback_state(True, estimated_rms=1500.0)
    assert ww._should_feed_wakeword(echo_chunk) is False
    loud_human = np.full(480, 6000, dtype=np.int16).tobytes()
    assert ww._should_feed_wakeword(loud_human) is True

    # 4. Short noise transient (< min_speech_duration_s) resets cleanly instead of buffering 15s blank STT
    rec = Recognizer(
        {"language": "tr", "samplerate": 16000, "channels": 1, "min_speech_duration_s": 0.4, "silence_threshold": 130.0}
    )
    rec._ensure_model = lambda: None  # type: ignore[method-assign]
    rec._turn_engine = DynamicTurnTakingEngine(
        min_speech_duration_s=0.4, end_of_turn_silence_s=0.85, max_turn_timeout_s=12.0
    )
    rec_calls: list[bytes] = []
    monkeypatch.setattr(rec, "recognize_pcm", lambda pcm_b: rec_calls.append(pcm_b) or ("", "tr"))

    blip = np.full(480, 1500, dtype=np.int16).tobytes()  # ~30ms per chunk
    silence = np.zeros(480, dtype=np.int16).tobytes()
    # 3 noise chunks (~90ms < 0.4s) followed by 550 chunks (16.5s) of silence
    results = list(rec.run([blip] * 3 + [silence] * 550))
    assert results == []
    assert rec_calls == []


def test_stt_scoring_entity_preservation_alias_and_single_pass_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        online_stt,
        "sr",
        SimpleNamespace(AudioData=lambda pcm, sample_rate=16000, sample_width=2: (pcm, sample_rate, sample_width)),
    )
    monkeypatch.setattr(online_stt, "_recognizer", object())

    for tr_cand, en_cand, exp_lang in (
        ("tekrar araştır", "take me to the restaurant", "tr"),
        ("tekrar internette araştır", "take your Internet to roster", "tr"),
        ("Switch persona sentry", "Switch persona sentry", "en"),
        ("Switch persona sentry", "switch parts on a century", "en"),
    ):
        def _fake(_audio, tag: str, tr_t=tr_cand, en_t=en_cand):
            return (tr_t, tag) if tag.startswith("tr") else (en_t, tag)

        monkeypatch.setattr(online_stt, "transcribe_single_language", _fake)
        text, lang = online_stt.transcribe_google_multilang(
            b"\x01\x00" * 2000, languages=["tr", "en"], default_lang="tr"
        )
        assert lang == exp_lang, f"Expected {exp_lang} for ({tr_cand!r} vs {en_cand!r}), got {lang!r}"

    # HybridTranslator preserves 'sentry', 'SentryBOT', and 'glados'
    tr = HybridTranslator({"enabled": True, "mode": "online_first", "cache_size": 8})
    monkeypatch.setattr(
        tr._online,
        "translate",
        lambda protected, src, tgt: f"Şu anda '{protected.split()[0]}' aktif.",
    )
    out, _ = tr.translate_with_meta("sentry active", "en", "tr")
    assert "sentry" in out
    assert "nöbetçi" not in out

    # Turkish spoken 'nöbetçi ye geç' still resolves to 'sentry' persona alias
    mgr = PersonaManager("modules/ai_provider/config/personalities")
    try:
        parsed = SpeechReactMixin._parse_persona_voice_command("nöbetçi ye geç", personas=mgr.list_personas())
        assert parsed == ("sentry", "")
    finally:
        mgr.close()

    # Streaming + bridge translation translates once per chunk and reuses chunks for final_text
    agent = _make_bare_agent(tmp_path, monkeypatch)
    agent.config["translation"] = {"enabled": True}
    agent.translator = HybridTranslator({"enabled": True, "mode": "online_first", "cache_size": 16})
    translate_calls: list[tuple[str, str, str]] = []

    def _fake_translate(txt: str, src: str, tgt: str):
        translate_calls.append((txt, src, tgt))
        return f"TR:{txt}" if src == "en" else f"EN:{txt}", "mock"

    monkeypatch.setattr(agent.translator, "translate_with_meta", _fake_translate)
    agent.apply_persona("sentry", notify=False, trigger_emotion=False)
    agent.ollama_client = MagicMock()
    agent.ollama_client.chat.return_value = iter([{"message": {"content": "Hello human."}}])
    agent._pick_runtime_model = lambda m: m  # type: ignore[method-assign]

    res = agent.step("merhaba", language="tr", native_tools=True)
    try:
        assert res is not None and res["text"] == "TR:Hello human."
        # Must translate user input -> EN once and streamed output -> TR once (NOT twice!)
        en_to_tr = [c for c in translate_calls if c[1] == "en" and c[2] == "tr"]
        assert len(en_to_tr) == 1
    finally:
        agent._close_persona_runtime()
        agent.tool_registry.close()


def test_stage_directions_markdown_and_emoji_filtered_from_tts() -> None:
    assert (
        strip_speech_control_artifacts(
            "🍰(Başımı hafifçe yana çevirir, sanki bu bilgi beni yormuş gibi) Merhaba *dostum* 🤞"
        )
        == "Merhaba dostum"
    )
    assert strip_speech_control_artifacts("(Sentezlenmiş, kuru ve hafif küçümseyici bir ton)") == ""
    assert strip_speech_control_artifacts("🤞") == ""
    assert "Emir HAMURCU (WhoIsMrSentry)" == strip_speech_control_artifacts("Emir HAMURCU (WhoIsMrSentry)")

    # Streaming buffer does not split mid-parenthesis
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    chunks, rem = agent._extract_ready_sentences(
        "🍰(Başımı hafifçe yana çevirir,", is_first_chunk=True, allow_first_clause_split=True
    )
    assert chunks == []
    assert "Başımı" in rem

    # /speak/say_stream gracefully skips bare emojis without raising
    svc = SpeakService()
    app = FastAPI()
    app.include_router(get_speak_router(svc))
    client = TestClient(app)
    r = client.post("/speak/say_stream", json={"text": "🤞", "language": "tr"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["skipped"] is True


def test_web_search_simplifies_queries_and_rust_logs_silenced(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _simplify_search_query("Yaratıcın Emir Hamurcu kimdir") == "Emir Hamurcu"

    backends_tried: list[tuple[str, str]] = []

    def _fake_ddgs(q: str, _max_r: int, backend: str):
        backends_tried.append((q, backend))
        if q == "Emir Hamurcu" and backend == "bing":
            return [{"title": "Emir Hamurcu", "url": "https://example.com", "snippet": "Creator"}]
        return []

    monkeypatch.setattr("modules.common.web_extractor._ddgs_text_with_backend", _fake_ddgs)
    res = search_web_headless("Yaratıcın Emir Hamurcu kimdir", max_results=3)
    assert res["ok"] is True
    assert res["results"][0]["title"] == "Emir Hamurcu"
    assert ("Emir Hamurcu", "bing") in backends_tried

    log_cfg = yaml.safe_load(
        Path("modules/runtime_console/logwrapper/config/config.yml").read_text(encoding="utf-8")
    )
    mod_levels = log_cfg.get("module_levels", {})
    for noisy_mod in ("primp", "h2", "hickory_resolver", "hickory_net", "cookie_store", "ddgs"):
        assert mod_levels.get(noisy_mod) == "WARNING"


def test_system1_safe_thresholds_and_silent_emotion_command_check(caplog: pytest.LogCaptureFixture) -> None:
    agent_cfg = yaml.safe_load(Path("config/agent.yaml").read_text(encoding="utf-8"))
    embed_cfg = agent_cfg["tri_layer"]["system1"]["embed"]
    assert float(embed_cfg["threshold_direct"]) >= 0.78

    with caplog.at_level(logging.DEBUG, logger="common.emotion_vocab"):
        assert SpeechReactMixin._emotion_command_for_text("Neymar") is None
        assert SpeechReactMixin._emotion_command_for_text("change") is None
    assert not [r for r in caplog.records if "Unknown emotion label" in r.message]

    from modules.agent_core.services.system1_embed import System1EmbedEngine

    eng = System1EmbedEngine.get_instance()
    if eng.is_available:
        d_retry = eng.decide("Tekrar dene")
        assert d_retry is None or not (d_retry.target_module == "emergency_stop" and d_retry.is_direct_command)
        d_web = eng.decide("yaratıcının internette araştır")
        assert d_web is None or not (d_web.target_module == "camera" and d_web.is_direct_command)


def test_readiness_head_adapter_and_lcd_sync_cooldown_behavior() -> None:
    try:
        readiness.mark_gateway_stopping()
        assert readiness.is_gateway_stopping() is True

        class _SpeechCli(ClientSpeechMixin):
            def __init__(self) -> None:
                self.speech_stream_cfg = {"use_stream_tts": True, "stream_poll_interval_s": 0.05}
                self.speech_quiet_cfg = {}
                self.offline_cfg = {}
                self.request_timeouts = {}

            @staticmethod
            def _post(service, endpoint, payload, timeout_s=1.0):
                return {"ok": True, "job_id": "job1"}

            @staticmethod
            def _get(*_a, **_k):
                raise AssertionError("Must not poll /jobs when gateway is stopping")

        res = _SpeechCli().speak_stream("Merhaba")
        assert res["status"] == "interrupted"

        sent = []
        sync = SpeechLcdSync({"enabled": True}, send_fn=lambda p: sent.append(p) or True)
        # With requests path active during gateway_stopping, _dispatch_payload must short-circuit
        sync._send_fn = None
        assert sync._dispatch_payload({"cmd": "lcd", "l1": "hi", "l2": "", "l3": "", "l4": ""}) is False
        assert sent == []
    finally:
        readiness.mark_gateway_idle()

    # HeadAdapter honors 404 cooldown and enabled=False without spamming
    adapter = HeadAdapter("http://127.0.0.1:8080", fail_cooldown_s=30.0)
    calls = {"n": 0}

    async def _post_404(*_a, **_k):
        calls["n"] += 1
        return SimpleNamespace(status_code=404)

    adapter._client = SimpleNamespace(post=_post_404)
    assert asyncio.run(adapter.move_head(90, 90)) is False
    calls_after_first = calls["n"]
    assert asyncio.run(adapter.move_head(95, 95)) is False
    assert calls["n"] == calls_after_first

    disabled = HeadAdapter("http://127.0.0.1:8080", enabled=False)
    disabled._client = SimpleNamespace(post=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("disabled")))
    assert asyncio.run(disabled.move_head(90, 90)) is False
