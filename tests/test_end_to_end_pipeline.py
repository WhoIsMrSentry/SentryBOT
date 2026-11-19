"""Behavioral end-to-end pipeline tests replacing legacy `tests/integration_test.py`."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.agent_core.api.core import get_core_router
from modules.agent_core.services.agent import AgentOrchestrator
from modules.agent_core.services.memory_consolidator import MemoryConsolidator
from modules.autonomy.services.brain import AutonomyBrain
from modules.autonomy.services.client import ServiceClient
from modules.common.emotion_vocab import Emotion, get_vocab
from modules.common.system_prompts import (
    get_default_persona_prompt,
    persona_prompt_with_language,
    resolve_persona_prompt,
)
from modules.expression.semantic.services.arbitrator import ExpressionArbiter, ModalityClients


def test_emotion_vocab_and_expression_arbiter_pipeline():
    vocab = get_vocab()
    for emo in (Emotion.ANGER, Emotion.JOY, Emotion.CURIOSITY, Emotion.FEAR):
        render = vocab.render(emo)
        assert render.canonical == emo
        assert render.neopixel_effect
        assert len(render.neopixel_rgb) == 3
        assert render.oled_animation
        assert render.voice_tone

    assert vocab.canonical("kork") == Emotion.FEAR
    assert vocab.canonical("merak") == Emotion.CURIOSITY
    assert vocab.canonical("sinirlen") == Emotion.ANGER
    assert vocab.canonical("mutlu ol") == Emotion.JOY

    arb = ExpressionArbiter(ModalityClients())
    result = asyncio.run(
        arb.express_emotion(
            emotion="anger",
            intensity=1.5,
            duration_s=0.1,
            modalities=["leds", "oled"],
            force=True,
        )
    )
    assert result["ok"] is True
    assert result["emotion"] == "anger"


def test_system_prompts_pipeline():
    prompt = get_default_persona_prompt()
    assert "express_emotion" in prompt
    assert "joy" in prompt
    custom_resolved = resolve_persona_prompt("Custom persona")
    assert custom_resolved.startswith("Custom persona")
    assert "EMBODIED ROBOT HARDWARE" in custom_resolved
    assert "express_emotion" in custom_resolved
    no_tools_resolved = resolve_persona_prompt("Custom persona", include_tools=False)
    assert no_tools_resolved.startswith("Custom persona")
    assert "EMBODIED ROBOT HARDWARE" in no_tools_resolved
    assert "TOOLS ARE ACTIONS" not in no_tools_resolved
    assert "[ Dil: Turkce ]" in persona_prompt_with_language(None, "[ Dil: Turkce ]")


def test_memory_consolidator_pipeline():
    consolidator = MemoryConsolidator()
    facts = consolidator.extract_facts("Benim adim Ahmet, ben doktorum ve Istanbul'da yasiyorum.")
    assert "user name is Ahmet" in facts

    recorded: list[tuple[str, str, float]] = []
    consolidator.memory = SimpleNamespace(
        remember=lambda kind, text, importance: recorded.append((kind, text, float(importance))),
    )
    result = consolidator.consolidate("My name is John and I like cats.", speaker="John")
    assert "user name is John" in result
    assert recorded


def test_agent_orchestrator_step_and_step_event_pipeline():
    orch = AgentOrchestrator(config={"llm": {"enabled": False}})
    assert orch.memory_consolidator is not None
    assert hasattr(orch, "autonomy_client")

    calls: list[tuple[str, str]] = []
    orch.ollama_client = SimpleNamespace(
        chat=lambda **kw: {
            "message": {
                "content": '{"thought": "ok", "speech": "Test yaniti.", "emotion": "joy"}'
            }
        }
    )
    orch._synthesize_persona_response = lambda **kw: "Test yaniti."  # type: ignore[method-assign]
    orch._run_subagent = lambda *a, **kw: {"ok": True, "summary": "ok"}  # type: ignore[method-assign]
    orch._post_speak = lambda text, **kw: calls.append(("speak", text))  # type: ignore[method-assign]

    step_res = orch.step("Merhaba", language="tr", speaker="Ali", trace_id="trace-step-1")
    assert isinstance(step_res, dict)
    assert step_res.get("text")

    event_res = orch.step_event("owner_seen", "Ali odaya girdi", language="tr", speaker="Ali", trace_id="trace-evt-1")
    assert isinstance(event_res, dict)
    assert event_res.get("text")


def test_autonomy_client_and_core_api_endpoints():
    client = ServiceClient({})
    for method in (
        "async_express_emotion",
        "async_move_head",
        "async_look_around",
        "async_get_vision",
        "async_speak",
        "async_remember_person",
        "async_search_memory",
        "async_focus_person",
        "async_wake",
        "async_sleep",
        "async_set_operational_mode",
        "async_queue_action",
        "async_push_interaction_event",
        "async_chat",
        "async_emote_neopixel",
        "async_set_neopixel",
        "async_animate",
        "async_close",
    ):
        assert callable(getattr(client, method))
    assert "gateway" in client.urls

    agent = SimpleNamespace(
        is_busy=False,
        api_native_tools=False,
        config={},
        status_interval_s=2.0,
        step=lambda query, native_tools=False, trace_id=None, language=None, speaker=None: {
            "text": f"echo:{query}",
            "trace_id": trace_id,
        },
        step_event=lambda event_type, event_prompt, language=None, speaker=None, trace_id=None: {
            "text": f"event:{event_type}",
            "trace_id": trace_id,
        },
        route_preview=lambda query: {"route": "test"},
        speech_arbiter=SimpleNamespace(interrupt_all=lambda: True),
    )
    app = FastAPI()
    app.include_router(get_core_router(agent))
    tc = TestClient(app)
    assert tc.get("/healthz").status_code == 200
    assert tc.get("/latency/latest").status_code == 200
    r_step = tc.post("/step", json={"query": "selam", "trace_id": "t1"})
    assert r_step.status_code == 200
    assert r_step.json()["text"] == "echo:selam"
    r_evt = tc.post("/step_event", json={"event_type": "sound_detected", "event_prompt": "Ses geldi", "trace_id": "t2"})
    assert r_evt.status_code == 200
    assert r_evt.json()["text"] == "event:sound_detected"


def test_autonomy_brain_sound_vision_and_decision_behavior():
    brain = AutonomyBrain({"defaults": {"loop_interval_ms": 200}, "llm": {"enabled": False}})
    emitted: list[tuple] = []

    fake_client = SimpleNamespace(
        move_head=lambda pan, tilt, speed=0.8: emitted.append(("move_head", pan)) or {"ok": True},
        speak=lambda text, **kw: emitted.append(("speak", text)) or {"ok": True},
        speak_preferred=lambda text, **kw: emitted.append(("speak", text)) or {"ok": True},
        push_interaction_event=lambda ev: emitted.append(("event", ev)) or {"ok": True},
        update_emotions=lambda emo: emitted.append(("emotions", emo)) or {"ok": True},
        queue_action=lambda action_type, **kw: emitted.append(("queue_action", action_type)) or {"ok": True},
        agent_step_event=lambda event_type, event_prompt, **kw: emitted.append(("step_event", event_type)) or {"text": "duydum"},
        agent_step=lambda *a, **kw: emitted.append(("agent_step", a[0] if a else "")) or {"text": "karar"},
        express_emotion=lambda emotion, **kw: emitted.append(("express_emotion", emotion)) or {"ok": True},
        is_service_available=lambda name: True,
        get_vision_context=lambda: {"objects": [], "faces": [], "hazards": []},
    )
    brain.client = fake_client

    # Verify real behavioral execution of sound reaction without source-string inspection
    brain._last_sound_react_ts = 0.0
    brain._react_to_sound(22.0)
    assert any(item[0] in {"move_head", "step_event", "queue_action", "event", "speak"} for item in emitted)

    # Verify forward visual events & agentic decision run cleanly without errors
    try:
        emitted.clear()
        brain._forward_visual_events_to_agent()
        brain._make_agentic_decision(reason="boredom", context_note="unit test")
        assert brain.mood is not None
    finally:
        brain.stop()
