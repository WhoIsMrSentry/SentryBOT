"""Iteration 17 unit & integration tests for modules/agent_core core & API (Birim 29)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from modules.agent_core import config_loader as agent_cfg_loader
from modules.agent_core import xAgentCoreService as x_agent_mod
from modules.agent_core.api.core import get_core_router
from modules.agent_core.services.action_arbiter import ActionArbiter, ActionRequest
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.agent_context import _PriorityOllamaAdapter
from modules.agent_core.services.memory_consolidator import MemoryConsolidator
from modules.agent_core.services.progress import ProgressManager
from modules.agent_core.services.semantic_index import tokenize as sem_tokenize
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.speech_arbiter import SpeechArbiter
from modules.agent_core.services.system1_cascade import System1CascadeEngine
from modules.agent_core.services.tri_layer import SubAgentProfile
from modules.agent_core.services.world_state import WorldState
from modules.common.model_policy import get_model_policy, set_required_model, set_strict_single_model


def test_ollama_priority_adapter_and_provider_availability_dict():
    called = {}

    class StrictOllamaClient:
        def chat(self, model, messages, options=None):
            called["model"] = model
            called["messages"] = messages
            return {"message": {"role": "assistant", "content": "selam"}}

        def list(self):
            return {"models": [{"name": "qwen3.5:9b"}]}

    adapter = _PriorityOllamaAdapter(StrictOllamaClient())
    resp = adapter.chat(model="qwen3.5:9b", messages=[{"role": "user", "content": "hi"}], priority=0)
    assert resp["message"]["content"] == "selam"

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.llm_provider = "ollama"
    agent.clm_fallback_enabled = False
    agent.clm_fallback_model = ""
    agent.fallback_on_error = False
    agent.fallback_on_missing_model = False
    agent.ollama_client = StrictOllamaClient()  # Even un-wrapped strict client works without TypeError
    out = agent._chat_turn("qwen3.5:9b", [{"role": "user", "content": "hi"}], tools=None, options=None)
    assert out["message"]["content"] == "selam"

    agent.llm_provider = "google_ai_studio"
    agent.provider_client = None
    err_dict = agent._check_provider_availability()
    assert isinstance(err_dict, dict)
    assert err_dict["ok"] is False
    assert err_dict["error"] == "provider_unavailable"


def test_streaming_works_with_tools_and_reads_persona_stream_key(monkeypatch):
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.persona_stream_enabled = True
    agent.llm_provider = "ollama"
    agent._pick_runtime_model = lambda m: m  # type: ignore
    agent.ollama_client = MagicMock()
    agent.ollama_client.chat.return_value = iter(
        [{"message": {"content": "Harika! "}}, {"message": {"content": "Yardım ediyorum."}}]
    )
    sentences = []
    out = agent._chat_maybe_stream(
        "qwen3.5:9b",
        [{"role": "user", "content": "yardım et"}],
        tools=[{"type": "function", "function": {"name": "speak"}}],
        options={"num_predict": 32},
        on_sentence=lambda s, idx: sentences.append((idx, s)),
    )
    assert out["message"]["content"] == "Harika! Yardım ediyorum."
    assert len(sentences) >= 2

    # Streamed tool call does not speak gibberish and preserves tool_calls
    agent.ollama_client.chat.return_value = iter(
        [{"message": {"content": "", "tool_calls": [{"function": {"name": "speak", "arguments": {"text": "hi"}}}]}}]
    )
    spoken_tc = []
    out_tc = agent._chat_maybe_stream(
        "qwen3.5:9b",
        [{"role": "user", "content": "speak hi"}],
        tools=[{"type": "function", "function": {"name": "speak"}}],
        options={},
        on_sentence=lambda s, idx: spoken_tc.append(s),
    )
    assert spoken_tc == []
    assert out_tc["message"]["tool_calls"][0]["function"]["name"] == "speak"

    # agent_context reads persona.stream fallback key
    agent2 = AgentOrchestrator.__new__(AgentOrchestrator)
    agent2._vision_input_available = lambda: False  # type: ignore
    agent2.sensor_loop = SimpleNamespace(laya_engine=None)
    monkeypatch.setattr("modules.agent_core.services.laya_engine.LayaEngine.get_instance", lambda _c: None)
    agent2._init_tri_layer({"tri_layer": {"persona": {"stream": True}}}, {})
    assert agent2.persona_stream_enabled is True


def test_tri_layer_no_env_mutation_and_subagent_allowed_tools_and_model():
    clean_env = {k: v for k, v in os.environ.items() if k not in {"OLLAMA_HOST", "OLLAMA_BASE_URL"}}
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, modules.agent_core.services.tri_layer; assert 'OLLAMA_HOST' not in os.environ and 'OLLAMA_BASE_URL' not in os.environ",
        ],
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert probe.returncode == 0, probe.stderr

    prof = SubAgentProfile(
        module="demo",
        role="Helper",
        goal="Inspect",
        allowed_tools=("get_sensor_data",),
        keywords=("sensor",),
    )
    assert prof.max_tokens == prof.num_predict
    assert prof.tools == ["get_sensor_data"]
    assert prof.keep_alive == "5m"

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.model = "custom-model:latest"
    agent.persona_system_prompt = "Bot"
    agent.temperature = 0.2
    agent.persona_num_predict = 64
    agent.num_ctx = 2048
    agent.persona_stream_enabled = False
    agent.tool_registry = MagicMock()
    agent.tool_registry.get_tool_schema.return_value = [{"type": "function", "function": {"name": "get_sensor_data"}}]
    agent.tool_registry.execute.return_value = "Battery: 95%."
    chat_calls = []

    def _fake_chat(model, messages, tools=None, options=None):
        chat_calls.append((model, tools))
        if tools:
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "get_sensor_data", "arguments": {}}}]}}
        return {"message": {"content": "Batarya %95."}}

    agent._chat_turn = _fake_chat  # type: ignore
    rep = agent._run_subagent_task(prof, "Pil ne durumda?")
    assert rep["text"] == "Batarya %95."
    assert len(rep["actions"]) == 1
    assert chat_calls[0][1] is not None

    agent._synthesize_persona_response("Pil?", [rep])
    assert chat_calls[-1][0] == "custom-model:latest"


def test_speech_arbiter_interrupt_idle_and_action_arbiter_real_priority(capsys):
    spoken = []
    arbiter = SpeechArbiter(speak_fn=lambda text, **_k: spoken.append(text))
    arbiter.start()
    try:
        # Interrupt while worker is idle must NOT drop subsequent speech
        arbiter.interrupt_all()
        arbiter.enqueue("Birinci cümle", priority=80, category="final")
        deadline = time.monotonic() + 2.0
        while not spoken and time.monotonic() < deadline:
            time.sleep(0.02)
        assert spoken == ["Birinci cümle"]
        # Must not print directly to stdout
        assert "[SentryBOT Speak]" not in capsys.readouterr().out
    finally:
        arbiter.stop()

    aa = ActionArbiter(default_cooldown_s=0.1)
    # agent_core acquires lock with high priority=90; manual with priority=75 must NOT override
    r1 = aa.submit(ActionRequest(type="head_move", source="agent_core", priority=90, ttl_ms=5000, payload={"pan": 90}))
    assert r1["ok"] is True
    r2 = aa.submit(ActionRequest(type="head_move", source="manual", priority=75, ttl_ms=5000, payload={"pan": 45}))
    assert r2["ok"] is False
    assert r2["reason"] == "resource_locked"


def test_thread_safety_model_policy_dry_and_lifespan_shutdown(tmp_path):
    # WorldState & ProgressManager thread-safe concurrent access
    ws = WorldState()
    pm = ProgressManager()
    errors = []

    def _worker():
        try:
            for i in range(40):
                ws.update_state({"distance_front_cm": i})
                assert "[SYSTEM WORLD STATE]" in ws.inject_world_state("Prompt")
                tok = pm.new_request("tr")
                pm.on_progress_event({"type": "status", "token": tok, "text": f"step {i}"})
                pm.get_latest_event()
                pm.emit_final(tok)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors

    # TopologicalMap atomic save_map
    slam = TopologicalMap(map_file=str(tmp_path / "map.json"))
    slam.save_map()
    assert (tmp_path / "map.json").exists()

    # model_policy DRY: disabling strict policy in common allows custom model in agent_core
    policy = get_model_policy()
    orig_req = getattr(policy, "_required_model", "qwen3.5:9b")
    orig_strict = getattr(policy, "_strict_single_model", True)
    try:
        set_required_model("custom-local:7b")
        set_strict_single_model(False)
        agent_cfg_loader._raise_if_bad_model("other:3b", "agent.model")
    finally:
        set_required_model(orig_req)
        set_strict_single_model(orig_strict)

    # xAgentCoreService.create_app() lifespan calls agent.stop()
    orig_cls = x_agent_mod.AgentOrchestrator
    stopped = {"called": False}

    class StubOrch:
        is_busy = False

        def __init__(self, _cfg):
            pass

        def start(self):
            pass

        def stop(self):
            stopped["called"] = True

    x_agent_mod.AgentOrchestrator = StubOrch  # type: ignore[misc]
    try:
        app = x_agent_mod.create_app()
        with TestClient(app) as client:
            assert client.get("/agent/healthz").status_code == 200
        assert stopped["called"] is True
    finally:
        x_agent_mod.AgentOrchestrator = orig_cls  # type: ignore[misc]


def test_memory_consolidator_semantic_dry_and_shared_step_core(monkeypatch):
    # No duplicate _SIMPLE_FACT_PATTERNS on MemoryConsolidator; still extracts via PreferenceLearner
    import modules.agent_core.services.memory_consolidator as mc_mod

    assert not hasattr(mc_mod, "_SIMPLE_FACT_PATTERNS")
    mc = MemoryConsolidator()
    assert "user name is Ali" in mc.extract_facts("benim adim Ali")
    assert sem_tokenize("kitapların")  # exercises shared cognitive_memory text_utils

    # Unified _run_turn_core in step() + step_event(): clean chat_history user+assistant pairs,
    # speaker propagation in step_event(), single per-turn lang_detect call, and /agent/step tri_layer
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = {"llm": {"model": "qwen3.5:9b"}}
    agent.is_busy = False
    agent.last_run = 0.0
    agent.cooldown = 0.0
    agent.max_history = 10
    agent.chat_history = []
    agent._history_lock = threading.RLock()
    agent.tri_layer_enabled = True
    agent.api_native_tools = True
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 10
    agent.fast_path_num_predict = 32
    agent.fast_path_max_steps = 2
    agent.max_steps = 4
    agent.temperature = 0.1
    agent.num_ctx = 2048
    agent.chat_num_predict = 64
    agent.persona_system_prompt = "Bot"
    agent.persona_num_predict = 64
    agent.persona_stream_enabled = False
    agent.last_routed_subagents = []
    agent.llm_provider = "ollama"
    agent.ollama_client = MagicMock()
    agent.world_state = WorldState()
    agent.memory = MagicMock()
    agent.memory_consolidator = MagicMock()
    agent.tool_registry = MagicMock()
    agent.tool_registry.status_hook = None
    agent.tool_registry.metrics.return_value = {}
    agent.progress_manager = ProgressManager()
    agent.speech_arbiter = SpeechArbiter()
    agent._active_progress_token = ""
    agent._active_laya_request_id = ""
    agent.check_survival_drives = lambda: None  # type: ignore
    agent._get_active_persona_model = lambda: "qwen3.5:9b"  # type: ignore
    agent._check_provider_availability = lambda: None  # type: ignore
    agent._get_world_memory_context = lambda _q="": "SECRET_WM_BLOB"  # type: ignore
    agent._run_tri_layer = lambda *_a, **_k: ("Tri Layer Cevabı", 1, [{"name": "core"}])  # type: ignore

    ev_res = agent.step_event("greeting", "Kullanıcıyı nazikçe selamla lütfen", speaker="Emre")
    assert ev_res and ev_res["text"] == "Tri Layer Cevabı"
    assert agent.world_state.get_state()["speaker"] == "Emre"
    # chat_history stores clean user + assistant pairs without [World State] / SECRET_WM_BLOB
    assert agent.chat_history[-2] == {"role": "user", "content": "Kullanıcıyı nazikçe selamla lütfen"}
    assert agent.chat_history[-1] == {"role": "assistant", "content": "Tri Layer Cevabı"}

    # Detect text language called at most once across 3 streamed sentences
    lang_calls = {"n": 0}
    monkeypatch.setattr(
        "modules.voice.speak.services.lang_detect.detect_text_language",
        lambda text, default="tr": (lang_calls.__setitem__("n", lang_calls["n"] + 1) or "tr"),
    )
    enqueued = []
    agent.speech_arbiter._speak_fn = lambda **kw: None
    agent.speech_arbiter.enqueue_final_chunk = lambda s, **_k: (enqueued.append(s) or "id1")  # type: ignore
    cb = agent._make_sentence_callback("tr", "t1", {"spoken": 0})
    assert cb is not None
    cb("Birinci cümle.", 0)
    cb("İkinci cümle.", 1)
    cb("Üçüncü cümle.", 2)
    assert len(enqueued) == 3
    assert lang_calls["n"] == 1

    # /step uses tri_layer when tri_layer_enabled=True and native_tools is omitted
    from fastapi import FastAPI

    api_app = FastAPI()
    api_app.include_router(get_core_router(agent), prefix="/agent")
    api_client = TestClient(api_app)
    r = api_client.post("/agent/step", json={"query": "Uzun planlama gerektiren bir soru soruyorum"})
    assert r.status_code == 200
    assert r.json()["text"] == "Tri Layer Cevabı"
    # Verify register_default_action_handlers binds a shared requests.Session closed by agent.stop()
    from modules.agent_core.services.agent_handlers import register_default_action_handlers

    agent.safety_filter = agent.world_state  # minimal stub if needed
    agent.action_arbiter = ActionArbiter()
    agent._gateway_base_url = "http://127.0.0.1:8999"
    agent._action_http_timeout_s = 1.0
    register_default_action_handlers(agent)
    assert getattr(agent, "_handler_http_session", None) is not None
    agent.sensor_loop = SimpleNamespace(stop=lambda: None)
    agent.idle_system = SimpleNamespace(stop=lambda: None)
    agent.stop()


def test_system1_cascade_lru_cache_and_healthz_summary(monkeypatch):
    from fastapi import FastAPI
    from modules.agent_core.services.laya_engine import LayaEngine

    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    raw_laya = LayaEngine.get_instance({"tri_layer": {"system1": {"backend": "laya"}}}, raw=True)
    cascade = System1CascadeEngine(
        raw_laya,
        {"enabled": True, "rules": {"enabled": True}, "embed": {"enabled": False}, "cache": {"max_entries": 4}},
    )
    d1 = cascade.decide("ışıkları kırmızı yak")
    d2 = cascade.decide("ışıkları kırmızı yak")
    assert d1 is not None and d2 is not None
    assert d1 is not d2  # Safe shallow copy
    _ = cascade.get_affective_reaction("joy", 0.5)
    _ = cascade.get_affective_reaction("joy", 0.5)
    stats = cascade.get_telemetry()["cache"]
    assert stats["hits"] >= 2
    assert stats["intent_entries"] == 1

    app = FastAPI()
    stub_agent = SimpleNamespace(
        is_busy=False,
        laya_engine=cascade,
        progress_manager=ProgressManager(),
        tool_registry=SimpleNamespace(metrics=lambda: {"speak": {"calls": 1, "errors": 0, "timeouts": 0}}),
    )
    app.include_router(get_core_router(stub_agent), prefix="/agent")
    res = TestClient(app).get("/agent/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["system1"]["backend"] == "cascade"
    assert data["system1"]["cache"]["hits"] >= 2
    assert "arbiters" in data
    assert data["tool_metrics"]["speak"]["calls"] == 1
    assert logging.getLogger("agent.orchestrator") is not None
