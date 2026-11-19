"""Unit tests for HybridTranslator (online Google + offline NMT fallback) and AgentCore bridge."""
from __future__ import annotations

from unittest.mock import MagicMock

from modules.agent_core.services.action_arbiter import ActionArbiter
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.agent_translation import split_companion_suffix
from modules.agent_core.services.memory import EpisodicMemory
from modules.agent_core.services.safety_filter import ActionSafetyFilter
from modules.agent_core.services.slam import TopologicalMap
from modules.agent_core.services.tools import ToolRegistry
from modules.agent_core.services.world_state import WorldState
from modules.common.translator import HybridTranslator


def test_hybrid_translator_online_then_offline_fallback(monkeypatch):
    tr = HybridTranslator(
        {"enabled": True, "mode": "online_first", "cache_size": 8, "fallback_to_ollama": False}
    )

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return [[["Hello world", "Merhaba dünya", None, None, 10]], None, "tr"]

    sess = MagicMock()
    sess.get.return_value = _Resp()
    tr._online._session = sess

    out, backend = tr.translate_with_meta("Merhaba dünya", "tr", "en")
    assert out == "Hello world"
    assert backend == "online_google"

    # Second call uses cache (no extra network hit)
    out2, _ = tr.translate_with_meta("Merhaba dünya", "tr", "en")
    assert out2 == "Hello world"
    assert sess.get.call_count == 1

    # Simulate network outage -> should trip cooldown and fall back to local NMT backend
    sess.get.side_effect = ConnectionError("offline")
    monkeypatch.setattr(tr._local, "translate", lambda text, s, t: (f"NMT:{text}", "local_ctranslate2"))

    out3, backend3 = tr.translate_with_meta("İkinci cümle", "tr", "en")
    assert out3 == "NMT:İkinci cümle"
    assert backend3 == "local_ctranslate2"
    assert tr._online.in_cooldown() is True


def test_split_companion_suffix_preserves_metadata():
    head, tail = split_companion_suffix("Bugün nasılsın?\n\n[CompanionContext speaker=Emir] trust=high")
    assert head == "Bugün nasılsın?"
    assert tail.startswith("\n\n[CompanionContext speaker=Emir]")


def test_agent_core_bridges_tr_to_en_and_back(monkeypatch):
    tr = HybridTranslator({"enabled": True, "mode": "local_only", "cache_size": 16})
    tr_map = {
        ("tr", "en", "Işıkları mavi yap"): "Turn the lights blue",
        ("en", "tr", "The lights are blue now."): "Işıklar artık mavi.",
        ("en", "tr", "Done in blue."): "Mavi olarak ayarlandı.",
    }
    monkeypatch.setattr(
        tr,
        "translate_with_meta",
        lambda text, src, tgt: (tr_map.get((src, tgt, text), text), "local_ctranslate2"),
    )

    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.config = {"agent": {}, "llm": {"provider": "ollama"}, "translation": {"enabled": True}}
    agent.model = "sentry:latest"
    agent.temperature = 0.1
    agent.num_ctx = 2048
    agent.chat_num_predict = 96
    agent.fast_path_enabled = True
    agent.fast_path_max_chars = 180
    agent.fast_path_num_predict = 96
    agent.fast_path_max_steps = 2
    agent.max_steps = 4
    agent.tri_layer_enabled = False
    agent.persona_system_prompt = ""
    agent.persona_stream_enabled = False
    agent.llm_provider = "ollama"
    agent.clm_fallback_enabled = False
    agent.clm_fallback_model = ""
    agent.fallback_on_missing_model = False
    agent.fallback_on_error = False
    agent.ollama_think = False
    agent.ollama_keep_alive = -1
    agent.chat_history = []
    agent.max_history = 10
    agent.cooldown = 0.0
    agent.last_run = 0.0
    agent.is_busy = False
    agent.last_routed_subagents = []
    agent.translator = tr
    agent.world_state = WorldState()
    agent.memory = EpisodicMemory(":memory:")
    agent.memory_consolidator = MagicMock()
    agent.memory_consolidator.get_context_summary.return_value = ""
    agent.progress_manager = MagicMock()
    agent.progress_manager.new_request.return_value = "tok"

    spoken_chunks = []
    agent.speech_arbiter = MagicMock()
    agent.speech_arbiter._speak_fn = lambda *_a, **_k: None
    agent.speech_arbiter.enqueue_final_chunk.side_effect = (
        lambda text, index=0, language="", **_k: spoken_chunks.append((text, language)) or "id1"
    )

    arbiter = ActionArbiter(safety_filter=ActionSafetyFilter())
    spoken_tool_calls = []
    arbiter.register_handler(
        "speak",
        lambda req: spoken_tool_calls.append((req.payload.get("text"), req.payload.get("language"))) or {"ok": True},
    )
    agent.action_arbiter = arbiter
    agent.tool_registry = ToolRegistry(
        None,
        agent.memory,
        TopologicalMap.__new__(TopologicalMap),
        agent.world_state,
        ActionSafetyFilter(),
        action_arbiter=arbiter,
        localize_speech_fn=agent._localize_tool_speech,
    )

    seen_messages = []

    def _fake_chat(model, messages, tools=None, options=None, **_kwargs):
        seen_messages.append(messages)
        if len(seen_messages) == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "speak", "arguments": {"text": "Done in blue.", "language": "en"}}}],
                }
            }
        return {"message": {"role": "assistant", "content": "The lights are blue now."}}

    monkeypatch.setattr(agent, "_check_provider_availability", lambda: None)
    monkeypatch.setattr(agent, "_chat_turn", _fake_chat)
    monkeypatch.setattr(agent, "_get_active_persona_model", lambda *_a: "sentry:latest")

    res = agent.step(
        "Işıkları mavi yap\n\n[CompanionContext speaker=Emir] trust=high",
        language="tr",
        native_tools=True,
    )
    assert res is not None
    assert res["text"] == "Işıklar artık mavi."
    assert "English" in seen_messages[0][0]["content"]
    assert seen_messages[0][1]["content"].startswith("Turn the lights blue")
    assert "[CompanionContext speaker=Emir]" in seen_messages[0][1]["content"]
    assert spoken_tool_calls == [("Mavi olarak ayarlandı.", "tr")]
    # Chat history preserves original Turkish text
    assert agent.chat_history[0]["content"].startswith("Işıkları mavi yap")
    assert agent.chat_history[1]["content"] == "Işıklar artık mavi."
