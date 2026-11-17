from __future__ import annotations

from types import SimpleNamespace
from fastapi import FastAPI
from starlette.testclient import TestClient
from unittest.mock import MagicMock

from modules.agent_core.config_loader import load_config as load_agent_core_config
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.agent_turn import _sentrybot_normalize_agent_turn_model
from modules.agent_core.services.memory_consolidator import MemoryConsolidator
from modules.agent_core.services.tri_layer import SubAgentProfile, TriLayerRouter, build_subagent_profiles
from modules.ai_provider.api import router as ai_router_mod
from modules.ai_provider.services.translator import OllamaTranslator
from modules.autonomy.services.behavior_planner import BehaviorPlanner, resolve_planner_llm_settings
from modules.autonomy.services.reflection_planner import ReflectionPlanner
from modules.common.config_loader import load_agent_config, load_ai_provider_config
from modules.common.model_roles import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_CODER_MODEL,
    DEFAULT_UTILITY_MODEL,
    DEFAULT_VISION_MODEL,
    infer_prompt_role,
    resolve_role_model,
)
from modules.vlm_bridge.config_loader import load_config as load_vlm_config
from modules.vlm_bridge.services.processor_identity_events import ProcessorIdentityEventsMixin
from modules.vlm_bridge.services.semantic_describer import SemanticDescriber


def test_real_agent_yaml_role_routing_isolation() -> None:
    root_cfg = load_agent_config()
    assert root_cfg["llm"]["single_model_mode"] is False
    assert root_cfg["agent"]["model"] == "sentry:latest"
    assert root_cfg["ollama"]["model"] == "sentry:latest"

    ai_cfg = load_ai_provider_config()
    assert ai_cfg["llm"]["single_model_mode"] is False
    assert ai_cfg["ollama"]["model"] == "sentry:latest"
    assert ai_cfg["translation"]["model"] == "nemotron-3.5-bolt:e4b"

    ac_cfg = load_agent_core_config()
    assert ac_cfg["llm"]["single_model_mode"] is False
    assert ac_cfg["agent"]["model"] == "sentry:latest"
    assert ac_cfg["ollama"]["model"] == "sentry:latest"

    vlm_cfg = load_vlm_config()
    assert vlm_cfg["llm"]["single_model_mode"] is False
    assert vlm_cfg["vision_llm"]["model"] == "qwen3.5:9b"
    assert vlm_cfg["ollama"]["model"] == "qwen3.5:9b"
    assert vlm_cfg["ollama"]["followup_model"] == "sentry:latest"

    # qwen3.5:9b is strictly scoped to visual description roles.
    for role in ("chat", "companion", "persona", "followup"):
        assert resolve_role_model(root_cfg, role) == "sentry:latest"
    for role in ("coder", "code", "developer", "technical"):
        assert resolve_role_model(root_cfg, role) == "qwen2.5-coder:7b"
    for role in ("utility", "planner", "reflection", "memory", "translator", "subagent"):
        assert resolve_role_model(root_cfg, role) == "nemotron-3.5-bolt:e4b"
    for role in ("vision", "vlm", "scene_description"):
        assert resolve_role_model(root_cfg, role) == "qwen3.5:9b"


def test_prompt_role_inference_keeps_identity_on_sentry_and_routes_coding_to_coder() -> None:
    assert infer_prompt_role("Lütfen kendini tanıt") == "chat"
    assert infer_prompt_role("Sen kimsin ve yeteneklerin neler?") == "chat"
    assert infer_prompt_role("Introduce yourself, what can you do?") == "chat"
    assert infer_prompt_role("Odada ne görüyorsun?") == "chat"

    assert infer_prompt_role("Bana Python ile quicksort fonksiyonu yaz") == "coder"
    assert infer_prompt_role("Bu Traceback SyntaxError hatasını debug et") == "coder"
    assert infer_prompt_role("Write a bash script to rotate logs") == "coder"
    assert _sentrybot_normalize_agent_turn_model(DEFAULT_CODER_MODEL) == DEFAULT_CODER_MODEL

    root_cfg = load_agent_config()
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = root_cfg
    agent.model = DEFAULT_CHAT_MODEL

    assert agent._get_active_persona_model("Lütfen kendini tanıt") == "sentry:latest"
    assert agent._get_active_persona_model("Bana Python script yaz") == "qwen2.5-coder:7b"


def test_background_planners_reflection_memory_and_tri_layer_roles() -> None:
    root_cfg = load_agent_config()

    planner_model, _, _ = resolve_planner_llm_settings(root_cfg)
    assert planner_model == DEFAULT_UTILITY_MODEL
    assert BehaviorPlanner(root_cfg).model == DEFAULT_UTILITY_MODEL
    assert ReflectionPlanner(root_cfg).model == DEFAULT_UTILITY_MODEL

    chat_calls = []

    class _FakeOllama:
        model = DEFAULT_CHAT_MODEL

        def chat(self, *, model=None, messages=None, options=None, **_kwargs):
            chat_calls.append(model)
            return {"message": {"content": "ok"}}

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = root_cfg
    agent.model = DEFAULT_CHAT_MODEL
    agent.provider_client = None
    agent.ollama_client = _FakeOllama()
    agent.generate_reflection("Son olayları özetle")
    assert chat_calls[-1] == "nemotron-3.5-bolt:e4b"

    # MemoryConsolidator constructed through AgentMemorySyncMixin receives utility model
    consolidator = agent._build_memory_consolidator()
    assert consolidator is not None
    assert consolidator.llm_model == "nemotron-3.5-bolt:e4b"

    mc_fallback = MemoryConsolidator(llm_client=_FakeOllama())
    assert mc_fallback is not None

    # TriLayer routing & subagent vs synthesizer model assignment
    profiles = build_subagent_profiles()
    assert "coder" in profiles
    router = TriLayerRouter(profiles=profiles, max_subagents=2)
    assert "coder" in router.route("python ile async fonksiyon debug et")

    agent.persona_system_prompt = "Sentry"
    agent.temperature = 0.15
    agent.persona_num_predict = 128
    agent.num_ctx = 4096
    agent.persona_stream_enabled = False
    agent.tool_registry = MagicMock()
    agent.tool_registry.get_tool_schema.return_value = []
    seen_models = []

    def _capture_turn(model, messages, tools=None, options=None):
        seen_models.append(model)
        return {"message": {"content": "tamam"}}

    agent._chat_turn = _capture_turn  # type: ignore
    agent._run_subagent_task(profiles["autonomy"], "Durumu kontrol et")
    assert seen_models[-1] == "nemotron-3.5-bolt:e4b"
    agent._run_subagent_task(profiles["coder"], "Python fonksiyonu yaz")
    assert seen_models[-1] == "qwen2.5-coder:7b"
    agent._run_subagent_task(SubAgentProfile(module="custom", role="R", goal="G", allowed_tools=(), keywords=(), model_override="qwen2.5-coder:7b"), "code")
    assert seen_models[-1] == "qwen2.5-coder:7b"
    agent._synthesize_persona_response("Merhaba", [{"module": "autonomy", "text": "hazır"}])
    assert seen_models[-1] == "sentry:latest"


def test_ai_provider_chat_role_routing_translator_and_vlm_followup_split(monkeypatch) -> None:
    calls = []

    class _FakeLLM:
        model = "sentry:latest"

        def list_models(self):
            return ["sentry:latest", "qwen3.5:9b", "nemotron-3.5-bolt:e4b", "qwen2.5-coder:7b"]

        def chat(self, messages, format=None, *, options=None, model=None):
            calls.append(model or self.model)
            return {"message": {"content": f"yanit ({model or self.model})"}}

        def chat_stream(self, messages, format=None, *, options=None, model=None):
            calls.append(model or self.model)
            yield {"delta": "parca", "done": True}

    fake = _FakeLLM()
    monkeypatch.setattr(ai_router_mod, "create_llm_client", lambda _cfg: (fake, "ollama"))

    ai_cfg = load_ai_provider_config()
    tr = OllamaTranslator(fake, ai_cfg["translation"])
    tr.cfg.enabled = True
    tr.translate("Merhaba dünya", "tr", "en")
    assert calls[-1] == "nemotron-3.5-bolt:e4b"

    app = FastAPI()
    app.include_router(ai_router_mod.get_router(ai_cfg))
    client = TestClient(app)

    r_default = client.post("/ollama/chat", params={"query": "Kendini tanıt"})
    assert r_default.status_code == 200
    assert r_default.json()["model"] == "sentry:latest"

    r_coder = client.post("/ollama/chat", params={"query": "Fibonacci yaz", "role": "coder"})
    assert r_coder.status_code == 200
    assert r_coder.json()["model"] == "qwen2.5-coder:7b"

    r_vision = client.post("/ollama/chat", params={"query": "Sahneyi özetle", "role": "vision"})
    assert r_vision.status_code == 200
    assert r_vision.json()["model"] == "qwen3.5:9b"

    r_bad = client.post("/ollama/chat", params={"query": "test", "model": "unlisted-model:1b"})
    assert r_bad.status_code == 400

    # VLM scene description uses qwen3.5:9b; companion greeting followup uses sentry:latest
    gen_calls = []
    monkeypatch.setattr(
        "modules.vlm_bridge.services.semantic_describer.generate_text",
        lambda prompt, cfg, **_k: (gen_calls.append(("semantic", cfg.get("model"))) or "Masa var."),
    )
    monkeypatch.setattr(
        "modules.vlm_bridge.services.processor_identity_events.generate_text",
        lambda prompt, cfg, **_k: (gen_calls.append(("followup", cfg.get("model"))) or "Hoş geldin Emir!"),
    )
    vlm_cfg = load_vlm_config()
    sd = SemanticDescriber(vlm_cfg)
    assert sd.llm_summarize([{"label": "cup"}]) == "Masa var."

    class _Identity(ProcessorIdentityEventsMixin):
        pass

    ident = _Identity()
    ident.config = vlm_cfg
    ident.memory = SimpleNamespace(get_person=lambda _name: {})
    assert ident._ollama_followup("Emir") == "Hoş geldin Emir!"

    assert ("semantic", "qwen3.5:9b") in gen_calls
    assert ("followup", "sentry:latest") in gen_calls
    assert DEFAULT_VISION_MODEL == "qwen3.5:9b"
