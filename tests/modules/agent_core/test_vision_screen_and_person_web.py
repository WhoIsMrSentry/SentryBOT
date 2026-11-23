from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.laya_engine import LayaEngine
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.progress import ProgressManager
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.speech_arbiter import SpeechArbiter
from modules.agent_core.services.system1_cascade import System1CascadeEngine
from modules.agent_core.services.system1_rules import classify
from modules.agent_core.services.tools.tool_registry import ToolRegistry
from modules.agent_core.services.tri_layer import build_subagent_profiles
from modules.agent_core.services.world_state import WorldState
from modules.common.system_prompts import get_hardware_core_prompt


def test_camera_screen_and_person_queries_route_without_2step_cap():
    for prompt in (
        "kameradaki kişi kim",
        "şuan ekranda ne görüyorsun",
        "ekranda hangi yazı var",
        "what is on the screen",
        "who is on camera",
    ):
        dec = classify(prompt)
        assert dec is not None, f"expected camera decision for {prompt!r}"
        assert dec.target_module == "camera"
        assert dec.is_direct_command is False
        assert dec.suggested_tool == "ask_vlm_about_scene"

    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    cascade = LayaEngine.get_instance(
        {"tri_layer": {"system1": {"backend": "cascade", "enabled": True, "embed": {"enabled": False}}}}
    )
    try:
        fast_ok, dec = cascade.should_fast_path("kameradaki kişi kim?")
        assert fast_ok is False
        assert dec is not None and dec.target_module == "camera"
    finally:
        System1CascadeEngine._instance = None


def test_tri_layer_and_system_prompt_include_vision_ocr_web_workflow():
    profiles = build_subagent_profiles()
    assert {"ask_vlm_about_scene", "read_text_ocr", "web_search", "fetch_webpage"} <= set(profiles["camera"].allowed_tools)
    assert {"ask_vlm_about_scene", "read_text_ocr", "web_search", "fetch_webpage"} <= set(profiles["vlm_bridge"].allowed_tools)

    prompt = get_hardware_core_prompt(include_tools=True)
    assert "ekranda ne görüyorsun" in prompt
    assert "read_text_ocr" in prompt
    assert "web_search" in prompt


def test_native_loop_chains_camera_vlm_then_web_search_for_short_person_query(monkeypatch):
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = {"llm": {"model": "sentry:latest"}, "tri_layer": {"fast_path": {"enabled": True, "max_chars": 180, "max_steps": 2}}}
    agent.is_busy = False
    agent.last_run = 0.0
    agent.cooldown = 0.0
    agent.max_history = 10
    agent.chat_history = []
    agent._history_lock = threading.RLock()
    agent.tri_layer_enabled = False
    agent.api_native_tools = True
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 180
    agent.fast_path_num_predict = 128
    agent.fast_path_max_steps = 2
    agent.max_steps = 4
    agent.temperature = 0.1
    agent.num_ctx = 4096
    agent.chat_num_predict = 256
    agent.persona_system_prompt = "Sentry"
    agent.persona_num_predict = 256
    agent.persona_stream_enabled = False
    agent.last_routed_subagents = []
    agent.llm_provider = "ollama"
    agent.clm_fallback_enabled = False
    agent.clm_fallback_model = ""
    agent.fallback_on_missing_model = False
    agent.fallback_on_error = False
    agent.ollama_think = False
    agent.ollama_keep_alive = -1
    agent._cached_model_names = []
    agent._cached_model_names_ts = 0.0
    agent.world_state = WorldState()
    agent.memory = EpisodicMemory(":memory:")
    agent.memory_consolidator = MagicMock()
    agent.progress_manager = ProgressManager()
    agent.speech_arbiter = SpeechArbiter()
    agent._active_progress_token = ""
    agent._active_laya_request_id = ""
    agent.check_survival_drives = lambda: None
    agent._get_active_persona_model = lambda: "sentry:latest"
    agent._check_provider_availability = lambda: None
    agent._get_world_memory_context = lambda _q="": ""

    LayaEngine._instance = None
    System1CascadeEngine._instance = None
    agent.laya_engine = LayaEngine.get_instance(
        {"tri_layer": {"system1": {"backend": "cascade", "enabled": True, "embed": {"enabled": False}}}}
    )

    reg = ToolRegistry(
        MagicMock(),
        agent.memory,
        TopologicalMap.__new__(TopologicalMap),
        agent.world_state,
        ActionSafetyFilter(),
    )
    reg._vision_input_available = lambda: True
    reg.tools["ask_vlm_about_scene"] = lambda question: "Ekranda Nikola Tesla görünüyor."
    reg.tools["web_search"] = lambda query, max_results=5: "1. Nikola Tesla — Sırp-Amerikalı mucit ve elektrik mühendisi."
    agent.tool_registry = reg

    turn_calls = []

    def _fake_call_ollama(_client, **_kwargs):
        step = len(turn_calls) + 1
        turn_calls.append(step)
        if step == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "ask_vlm_about_scene", "arguments": {"question": "kameradaki kişi kim"}}}]}}
        if step == 2:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "web_search", "arguments": {"query": "Nikola Tesla kimdir"}}}]}}
        return {"message": {"role": "assistant", "content": "Kamerada Nikola Tesla görünüyor; alternatif akım sistemlerinin öncüsü olan ünlü elektrik mühendisidir."}}

    import modules.agent_core.services.agent_turn as turn_mod

    monkeypatch.setattr(turn_mod, "call_ollama_chat", _fake_call_ollama)
    agent.ollama_client = SimpleNamespace(chat=lambda **kw: _fake_call_ollama(None, **kw))

    try:
        res = agent.step("kameradaki kişi kim?", language="tr", native_tools=True)
        assert res is not None
        assert len(turn_calls) == 3
        assert [a["tool"] for a in res["actions"]] == ["ask_vlm_about_scene", "web_search"]
        assert "Nikola Tesla" in res["text"]
    finally:
        reg.close()
        System1CascadeEngine._instance = None
