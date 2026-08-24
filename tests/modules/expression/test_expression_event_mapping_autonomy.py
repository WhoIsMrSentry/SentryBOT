from modules.expression.semantic.services.state import SemanticExpressionEngine


def state_after(engine, event, data=None):
    payload = engine.event(event, data or {})
    return payload["state"]


def test_autonomy_idle_actions_drive_expression_state():
    e = SemanticExpressionEngine()
    s = state_after(e, "autonomy.look_around")
    assert s["emotion"] == "curious"
    assert s["attention"] == "camera"
    s = state_after(e, "autonomy.blink")
    assert s["emotion"] == "neutral"
    assert s["attention"] == "idle"
    s = state_after(e, "autonomy.bored")
    assert s["emotion"] == "curious"
    assert s["attention"] == "internal"
    assert s["reason"] == "boredom"
    s = state_after(e, "autonomy.stretch")
    assert s["energy"] == "high"
    s = state_after(e, "autonomy.monologue")
    assert s["emotion"] == "thinking"


def test_companion_proactive_curiosity_alias():
    e = SemanticExpressionEngine()
    s = state_after(e, "companion.proactive", {"emotion": "curiosity", "text": "Merak ediyorum."})
    assert s["emotion"] == "curious"
    assert s["reason"].startswith("companion:")


def test_llm_unavailable_reduces_confidence_without_alerting():
    e = SemanticExpressionEngine()
    s = state_after(e, "error", {"source": "ollama", "reason": "chat_failed"})
    assert s["emotion"] == "thinking"
    assert s["confidence"] <= 0.3
    assert s["reason"] == "llm_unavailable"


def test_idle_behavior_selected_payload_mapping():
    e = SemanticExpressionEngine()
    s = state_after(e, "idle.behavior.selected", {"behavior": "LOOK_AROUND"})
    assert s["emotion"] == "curious"
    assert s["attention"] == "camera"
    s = state_after(e, "idle.behavior.selected", {"behavior": "SIGH"})
    assert s["emotion"] == "sleepy"
    assert s["energy"] == "low"


def test_interactions_metric_events_map_to_expression():
    e = SemanticExpressionEngine()
    s = state_after(e, "interactions.cpu_hot")
    assert s["emotion"] == "alert"
    assert s["reason"] == "cpu_hot"
    s = state_after(e, "interactions.idle")
    assert s["emotion"] == "neutral"
    assert s["attention"] == "idle"