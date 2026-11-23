"""Regression tests for empty LLM final steps after tool calls or thinking-only turns."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

from modules.agent_core.config_loader import load_config as load_agent_core_config
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.agent_turn import _extract_usable_reply
from modules.autonomy.services.brain import AutonomyBrain


def _make_agent() -> AgentOrchestrator:
    agent = AgentOrchestrator.__new__(AgentOrchestrator)
    agent.llm_provider = "ollama"
    agent.temperature = 0.15
    agent.chat_num_predict = 2048
    agent.num_ctx = 8192
    agent.persona_stream_enabled = False
    agent.ollama_think = True
    agent.ollama_keep_alive = -1
    agent.clm_fallback_enabled = False
    agent.clm_fallback_model = ""
    agent.fallback_on_missing_model = False
    agent.fallback_on_error = False
    agent.max_steps = 4
    agent._cached_model_names = []
    agent._cached_model_names_ts = 0.0
    agent._history_lock = threading.RLock()
    agent.chat_history = []
    agent.tool_registry = MagicMock()
    agent.tool_registry.get_tool_schema.return_value = [
        {"type": "function", "function": {"name": "express_emotion", "parameters": {"type": "object"}}}
    ]
    agent.tool_registry.get_tool_names.return_value = ["express_emotion"]
    agent.tool_registry.execute.return_value = (
        "Expressed curiosity (intensity=1.00, 2.0s) across leds, oled, voice, head."
    )
    return agent


def test_preserves_step1_spoken_text_when_step2_after_tool_is_empty() -> None:
    agent = _make_agent()
    responses = iter(
        [
            {
                "done_reason": "stop",
                "eval_count": 210,
                "message": {
                    "role": "assistant",
                    "content": "I'm sorry to hear that. What isn't helping right now?",
                    "tool_calls": [
                        {"function": {"name": "express_emotion", "arguments": {"emotion": "curiosity"}}}
                    ],
                },
            },
            {
                "done_reason": "stop",
                "eval_count": 76,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "I already replied in step 1.",
                },
            },
        ]
    )
    calls = []

    def _fake_chat(model, messages, tools, options, on_sentence=None):
        calls.append((tools is not None, len(messages)))
        return next(responses)

    agent._chat_maybe_stream = _fake_chat  # type: ignore[method-assign]
    actions = []
    final_text, steps = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "what's the matter isn't helping"}],
        actions_out=actions,
        max_steps=2,
    )
    assert steps == 2
    assert len(calls) == 2
    assert len(actions) == 1
    assert "What isn't helping right now?" in final_text


def test_runs_single_no_tool_recovery_when_all_steps_return_empty_content() -> None:
    agent = _make_agent()
    responses = iter(
        [
            {
                "done_reason": "stop",
                "eval_count": 120,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "express_emotion", "arguments": {"emotion": "curiosity"}}}
                    ],
                },
            },
            {
                "done_reason": "stop",
                "eval_count": 64,
                "message": {"role": "assistant", "content": ""},
            },
            {
                "done_reason": "stop",
                "eval_count": 48,
                "message": {
                    "role": "assistant",
                    "content": "Could you clarify what isn't helping?",
                },
            },
        ]
    )
    seen_tools = []

    def _fake_chat(model, messages, tools, options, on_sentence=None):
        seen_tools.append(tools)
        return next(responses)

    agent._chat_maybe_stream = _fake_chat  # type: ignore[method-assign]
    actions = []
    final_text, _ = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "what's the matter isn't helping"}],
        actions_out=actions,
        max_steps=2,
    )
    assert len(seen_tools) == 3
    assert seen_tools[-1] is None
    assert final_text == "Could you clarify what isn't helping?"


def test_runs_recovery_when_thinking_only_response_drops_content() -> None:
    agent = _make_agent()
    responses = iter(
        [
            {
                "done_reason": "stop",
                "eval_count": 318,
                "message": {"role": "assistant", "content": ""},
            },
            {
                "done_reason": "stop",
                "eval_count": 90,
                "message": {"role": "assistant", "content": "Hello! I'm Sentry."},
            },
        ]
    )
    seen_tools = []

    def _fake_chat(model, messages, tools, options, on_sentence=None):
        seen_tools.append(tools)
        return next(responses)

    agent._chat_maybe_stream = _fake_chat  # type: ignore[method-assign]
    final_text, _ = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "please introduce yourself"}],
        actions_out=[],
        max_steps=2,
    )
    assert len(seen_tools) == 2
    assert seen_tools[-1] is None
    assert final_text == "Hello! I'm Sentry."


def test_usable_reply_filters_raw_gemma_tool_text_and_bare_empty_mock() -> None:
    assert _extract_usable_reply('express_emotion{emotion:<|"|>confusion<|"|>}') == ""
    assert _extract_usable_reply("<think>internal</think>") == ""
    assert _extract_usable_reply("Normal answer.") == "Normal answer."

    agent = _make_agent()
    calls = 0

    def _bare_empty(*_a, **_kw):
        nonlocal calls
        calls += 1
        return {"message": {"content": ""}}

    agent._chat_maybe_stream = _bare_empty  # type: ignore[method-assign]
    final_text, _ = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "hi"}],
        actions_out=[],
        max_steps=2,
    )
    assert final_text == ""
    assert calls == 1


def test_vocal_falls_back_when_actions_exist_without_text_or_speech(tmp_path) -> None:
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
        brain.client = MagicMock()
        brain.agent = MagicMock()
        brain.agent.speech_arbiter._speak_fn = lambda *_a, **_k: None
        brain._active_speech_req_id = "req1"
        brain.agent.step.return_value = {
            "text": "",
            "speech_handled": False,
            "actions": [{"tool": "express_emotion", "result": "Expressed curiosity"}],
        }
        assert brain._try_agent_core_path("what's the matter", "en", None, "req1") is False

        # Full _react_to_speech fallback reaches client.chat when actions had no speech
        spoken_calls = []
        brain.client.chat.return_value = {"answer": "Could you tell me what isn't helping?"}
        brain.client.queue_action.side_effect = lambda kind, **_kw: spoken_calls.append(kind) or {"ok": True}
        brain._react_to_speech("what's the matter isn't helping", source_lang="en")
        brain.client.chat.assert_called_once()
        assert "speak" in spoken_calls

        brain._active_speech_req_id = "req2"
        brain.agent.step.return_value = {
            "text": "",
            "speech_handled": True,
            "actions": [{"tool": "speak", "result": "Speaking: hi"}],
        }
        assert brain._try_agent_core_path("merhaba", "tr", None, "req2") is True
    finally:
        brain.stop()


def test_think_and_stream_remain_enabled_and_chat_budget_not_capped_at_120() -> None:
    cfg = load_agent_core_config()
    assert cfg["llm"]["think"] is True
    assert cfg["tri_layer"]["persona"]["stream"] is True
    agent = AgentOrchestrator(cfg)
    try:
        assert agent.ollama_think is True
        assert agent.persona_stream_enabled is True
        assert agent.chat_num_predict >= 1024
    finally:
        agent.stop()


def test_streaming_preserves_eval_metadata_and_avoids_double_speak_across_steps() -> None:
    agent = _make_agent()
    agent.persona_stream_enabled = True
    agent._pick_runtime_model = lambda m: m  # type: ignore[method-assign]

    # Case 1: Empty stream with terminal eval_count/done_reason still triggers recovery
    stream_step1 = iter(
        [
            {"message": {"content": "", "thinking": "Thinking quietly..."}, "done": False},
            {"message": {"content": ""}, "done": True, "done_reason": "stop", "eval_count": 220},
        ]
    )
    stream_recovery = iter(
        [
            {"message": {"content": "Merhaba Emir!"}, "done": True, "done_reason": "stop", "eval_count": 20},
        ]
    )
    agent.ollama_client = MagicMock()
    agent.ollama_client.chat.side_effect = [stream_step1, stream_recovery]
    spoken: list[tuple[int, str]] = []
    final_text, _ = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "selam"}],
        actions_out=[],
        on_sentence=lambda s, i: spoken.append((i, s)),
        max_steps=2,
    )
    assert final_text == "Merhaba Emir!"
    assert spoken == [(0, "Merhaba Emir!")]

    # Case 2: Step 1 streams text before late tool_call; remainder flushes cleanly and Step 2 doesn't double-speak
    step1_late_tool = iter(
        [
            {"message": {"content": "I am sorry, "}, "done": False},
            {"message": {"content": "", "tool_calls": [{"function": {"name": "express_emotion", "arguments": {"emotion": "curiosity"}}}]}, "done": False},
            {"message": {"content": "tell me more."}, "done": True, "done_reason": "stop", "eval_count": 40},
        ]
    )
    step2_dup = {
        "message": {"content": "Please tell me more."},
        "done_reason": "stop",
        "eval_count": 15,
    }
    agent.ollama_client.chat.side_effect = [step1_late_tool, step2_dup]
    spoken2: list[tuple[int, str]] = []
    final_text2, _ = agent._run_native_history_loop(
        "sentry:latest",
        [{"role": "user", "content": "what is wrong"}],
        actions_out=[],
        on_sentence=lambda s, i: spoken2.append((i, s)),
        max_steps=2,
    )
    assert "tell me more." in " ".join(s for _, s in spoken2)
    assert not any("Please tell me more." == s for _, s in spoken2)
    assert final_text2 == "Please tell me more."
