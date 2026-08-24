from modules.expression.semantic.services.state import SemanticExpressionEngine


def state_after(event, data=None):
    engine = SemanticExpressionEngine()
    payload = engine.event(event, data or {})
    return payload["state"]


def test_needs_exploration_maps_to_curious_camera():
    s = state_after("needs.exploration", {"recommended_goal": "look_around_and_learn", "confidence": 0.82})
    assert s["emotion"] == "curious"
    assert s["attention"] == "camera"
    assert s["reason"] == "needs.exploration"
    assert s["confidence"] == 0.82


def test_needs_boredom_maps_to_internal_curiosity():
    s = state_after("needs.boredom", {"confidence": 0.88})
    assert s["emotion"] == "curious"
    assert s["attention"] == "internal"
    assert s["reason"] == "boredom"


def test_needs_social_rest_and_safety_have_distinct_moods():
    social = state_after("needs.social", {"confidence": 0.7})
    assert social["emotion"] == "happy"
    assert social["attention"] == "user"

    rest = state_after("needs.rest", {"confidence": 0.75})
    assert rest["emotion"] == "sleepy"
    assert rest["attention"] == "sleep"
    assert rest["energy"] == "low"

    safety = state_after("needs.safety", {"confidence": 0.9})
    assert safety["emotion"] == "alert"
    assert safety["arousal"] == "high"


def test_needs_balance_keeps_robot_calm():
    s = state_after("needs.balance", {"recommended_goal": "calm_idle", "confidence": 0.55})
    assert s["emotion"] == "neutral"
    assert s["attention"] == "idle"
    assert s["reason"] == "needs.balance"
    assert 0.45 <= s["confidence"] <= 0.7