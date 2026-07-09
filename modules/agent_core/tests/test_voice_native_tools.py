"""Voice path uses native tool loop regardless of prompt length."""

from unittest.mock import MagicMock

from modules.agent_core.services.agent import AgentOrchestrator


def _make_agent(**overrides) -> AgentOrchestrator:
    cfg = {
        "agent": {"model": "test", "cooldown_s": 0, "max_steps": 2},
        "llm": {"provider": "ollama"},
        "tri_layer": {"enabled": True, "fast_path": {"enabled": True, "max_chars": 20}},
        "actions": {"gateway_base_url": "http://127.0.0.1:8080"},
    }
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 20
    for key, value in overrides.items():
        setattr(agent, key, value)
    return agent


def test_native_tools_bypasses_char_limit():
    agent = _make_agent()
    long_prompt = "x" * 200
    assert not agent._should_fast_path(long_prompt)
    assert agent._should_fast_path(long_prompt, native_tools=True)


def test_native_tools_skips_tri_layer_in_step(monkeypatch):
    agent = _make_agent()
    agent.is_busy = False
    agent.last_run = 0
    agent.cooldown = 0
    agent.tri_layer_enabled = True
    agent.last_routed_subagents = []
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 10
    agent.fast_path_num_predict = 32
    agent.llm_provider = "ollama"
    agent.ollama_client = MagicMock()
    agent.persona_system_prompt = ""
    agent.chat_history = []
    agent.max_history = 10
    agent.temperature = 0.1
    agent.num_ctx = 2048
    agent.progress_manager = MagicMock()
    agent.progress_manager.new_request.return_value = "tok"
    agent.memory = MagicMock()
    agent.memory_consolidator = MagicMock()
    agent.tool_registry = MagicMock()
    agent.tool_registry.status_hook = None
    agent.speech_arbiter = MagicMock()
    agent.speech_arbiter._speak_fn = None
    agent.world_state = MagicMock()
    agent.world_state.inject_world_state.return_value = ""
    agent.config = {"llm": {"model": "test"}}
    agent._active_progress_token = None

    tri_layer_called = {"value": False}

    def _tri_layer(*_a, **_k):
        tri_layer_called["value"] = True
        return "tri", 1, []

    native_called = {"value": False}

    def _native_loop(*_a, **_k):
        native_called["value"] = True
        return "native", 1

    monkeypatch.setattr(agent, "check_survival_drives", lambda: None)
    monkeypatch.setattr(agent, "_get_active_persona_model", lambda: "test")
    monkeypatch.setattr(agent, "_check_provider_availability", lambda: None)
    monkeypatch.setattr(agent, "_run_tri_layer", _tri_layer)
    monkeypatch.setattr(agent, "_run_native_history_loop", _native_loop)
    monkeypatch.setattr(agent, "_append_history", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "_normalize_session_language", lambda _l: "en")
    monkeypatch.setattr(agent, "_build_progress_callback", lambda *_a, **_k: None)
    monkeypatch.setattr(agent, "_current_speaker", lambda: "")

    long_prompt = "Mach die LEDs rot und erzähl mir eine Geschichte über Roboter."
    agent.step(long_prompt, native_tools=True)

    assert native_called["value"]
    assert not tri_layer_called["value"]
