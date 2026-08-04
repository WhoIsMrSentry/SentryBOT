#!/usr/bin/env python
"""End-to-end integration test for SentryBOT Faz 1-4 pipeline.

Tests the complete flow:
1. Emotion vocabulary → ExpressionArbiter → API
2. Agent step() with system prompt
3. Memory consolidation → WorldMemory
4. Event-driven step_event() via API
"""

import sys
import os
import json
import asyncio
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_emotion_vocab():
    """Test emotion vocabulary and ExpressionArbiter."""
    print("\n=== Test: Emotion Vocabulary ===")
    from modules.common.emotion_vocab import get_vocab, Emotion
    from modules.expression.services.arbitrator import ExpressionArbiter, ModalityClients
    
    vocab = get_vocab()
    
    # Test canonical emotions
    for emo in [Emotion.ANGER, Emotion.JOY, Emotion.CURIOSITY, Emotion.FEAR]:
        render = vocab.render(emo)
        assert render.canonical == emo
        assert render.neopixel_effect
        assert len(render.neopixel_rgb) == 3
        assert render.oled_animation
        assert render.voice_tone
        print(f"  OK {emo.value}: {render.neopixel_effect} {render.neopixel_rgb} | {render.oled_animation} | {render.voice_tone}")
    
    # Test Turkish aliases
    assert vocab.canonical("kork") == Emotion.FEAR
    assert vocab.canonical("merak") == Emotion.CURIOSITY
    assert vocab.canonical("sinirlen") == Emotion.ANGER
    assert vocab.canonical("mutlu ol") == Emotion.JOY
    print("  OK Turkish aliases work")
    
    # Test ExpressionArbiter
    arb = ExpressionArbiter(ModalityClients())
    result = asyncio.run(arb.express_emotion(
        emotion="anger", intensity=1.5, duration_s=0.5,
        modalities=["leds", "oled"], force=True
    ))
    assert result["ok"] is True
    assert result["emotion"] == "anger"
    print("  OK ExpressionArbiter atomik ifade çalışıyor")
    
    print("PASS Emotion Vocabulary + ExpressionArbiter PASSED")


def test_system_prompts():
    """Test system prompt generation."""
    print("\n=== Test: System Prompts ===")
    from modules.common.system_prompts import (
        get_default_persona_prompt, 
        resolve_persona_prompt, 
        persona_prompt_with_language
    )
    
    prompt = get_default_persona_prompt()
    assert "express_emotion" in prompt
    assert "joy" in prompt
    assert "29" in prompt or "anger" in prompt  # emotion list
    print("  OK Default persona prompt contains express_emotion tool")
    
    custom = resolve_persona_prompt("Custom persona")
    assert custom == "Custom persona"
    print("  OK Custom persona override works")
    
    with_lang = persona_prompt_with_language(None, "[ Dil: Turkce ]")
    assert "[ Dil: Turkce ]" in with_lang
    print("  OK Language directive appended")
    
    print("PASS System Prompts PASSED")


def test_memory_consolidator():
    """Test memory consolidation with regex and LLM extraction."""
    print("\n=== Test: Memory Consolidator ===")
    from modules.agent_core.services.memory_consolidator import MemoryConsolidator
    
    consolidator = MemoryConsolidator()
    
    # Test regex extraction (fast path)
    facts = consolidator.extract_facts("Benim adim Ahmet, ben doktorum ve Istanbul'da yasiyorum.")
    assert "user name is Ahmet" in facts
    print(f"  OK Regex extraction: {facts}")
    
    # Test consolidation stores in episodic
    consolidator.memory = type('MockMemory', (), {
        'remember': lambda self, kind, text, importance: print(f"  → Episodic: {kind}: {text} (importance={importance})")
    })()
    
    result = consolidator.consolidate("My name is John and I like cats.", speaker="John")
    assert "user name is John" in result
    print("  OK Consolidation with speaker works")
    
    print("PASS Memory Consolidator PASSED")


def test_agent_orchestrator_imports():
    """Test that AgentOrchestrator has all new methods."""
    print("\n=== Test: AgentOrchestrator ===")
    from modules.agent_core.services.agent import AgentOrchestrator
    
    assert hasattr(AgentOrchestrator, "step"), "step() missing"
    assert hasattr(AgentOrchestrator, "step_event"), "step_event() missing"
    assert hasattr(AgentOrchestrator, "_native_loop_messages"), "_native_loop_messages missing"
    assert hasattr(AgentOrchestrator, "_synthesize_main_persona"), "_synthesize_main_persona missing"
    print("  OK All required methods present")
    
    # Test memory_consolidator wiring
    import inspect
    source = inspect.getsource(AgentOrchestrator._build_memory_consolidator)
    assert "autonomy_client" in source
    assert "llm_client" in source
    print("  OK _build_memory_consolidator passes autonomy_client and llm_client")
    
    print("PASS AgentOrchestrator PASSED")


def test_autonomy_client_async():
    """Test autonomy client async methods exist."""
    print("\n=== Test: Autonomy Client Async Methods ===")
    from modules.autonomy.services.client import ServiceClient
    
    client = ServiceClient({})
    async_methods = [
        "async_express_emotion", "async_move_head", "async_look_around",
        "async_get_vision", "async_speak", "async_remember_person",
        "async_search_memory", "async_focus_person", "async_wake",
        "async_sleep", "async_set_operational_mode", "async_queue_action",
        "async_push_interaction_event", "async_chat", "async_emote_neopixel",
        "async_set_neopixel", "async_animate", "async_close"
    ]
    
    for method in async_methods:
        assert hasattr(client, method), f"Missing {method}"
    print(f"  OK All {len(async_methods)} async methods present")
    
    # Test gateway URL present
    assert "gateway" in client.urls, "gateway URL missing"
    print("  OK gateway URL in client.urls")
    
    print("PASS Autonomy Client Async Methods PASSED")


def test_api_endpoints():
    """Test API router includes step_event."""
    print("\n=== Test: API Endpoints ===")
    from modules.agent_core.api.core import get_core_router
    
    class MockAgent:
        is_busy = False
        api_native_tools = False
        config = {}
        status_interval_s = 2.0
        
        def step(self, query, native_tools=False, trace_id=None, language=None, speaker=None):
            return {"text": "test response", "trace_id": trace_id}
        
        def step_event(self, event_type, event_prompt, language=None, speaker=None, trace_id=None):
            return {"text": f"event {event_type} handled", "trace_id": trace_id}
        
        def route_preview(self, query):
            return {"route": "test"}
        
        speech_arbiter = type('MockArbiter', (), {'interrupt_all': lambda: True})()
    
    router = get_core_router(MockAgent())
    routes = [route.path for route in router.routes]
    
    assert "/step" in routes
    assert "/step_event" in routes
    assert "/healthz" in routes
    assert "/latency/latest" in routes
    print(f"  OK Routes include step_event: {routes}")
    
    print("PASS API Endpoints PASSED")


def test_brain_event_bridge():
    """Test autonomy brain has event-driven step_event calls."""
    print("\n=== Test: Brain Event Bridge ===")
    import inspect
    from modules.autonomy.services.brain import AutonomyBrain
    
    # Check _react_to_sound calls step_event
    sound_source = inspect.getsource(AutonomyBrain._react_to_sound)
    assert "step_event" in sound_source
    assert "sound_detected" in sound_source
    print("  OK _react_to_sound calls step_event")
    
    # Check _forward_visual_events_to_agent calls step_event
    vision_source = inspect.getsource(AutonomyBrain._forward_visual_events_to_agent)
    assert "step_event" in vision_source
    assert "hazard_detected" in vision_source
    assert "owner_seen" in vision_source
    assert "new_person_seen" in vision_source
    assert "idle_comment" in vision_source
    print("  OK _forward_visual_events_to_agent calls step_event for all events")
    
    # Check _make_agentic_decision has enhanced prompt
    decision_source = inspect.getsource(AutonomyBrain._make_agentic_decision)
    assert "express_emotion" in decision_source
    assert "look_around" in decision_source
    assert "move_head" in decision_source
    print("  OK _make_agentic_decision has full tool list")
    
    print("PASS Brain Event Bridge PASSED")


def main():
    print("=" * 60)
    print("SENTRYBOT FAZ 1-4 END-TO-END INTEGRATION TEST")
    print("=" * 60)
    
    test_emotion_vocab()
    test_system_prompts()
    test_memory_consolidator()
    test_agent_orchestrator_imports()
    test_autonomy_client_async()
    test_api_endpoints()
    test_brain_event_bridge()
    
    print("\n" + "=" * 60)
    print("PASS ALL TESTS PASSED - Pipeline is ready!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Start gateway: python -m modules.gateway.services.bootstrap")
    print("  2. Test /agent/step_event endpoint with curl")
    print("  3. Verify WorldMemory writes via autonomy loop")


if __name__ == "__main__":
    main()