
from modules.autonomy.services.vision_context_needs_bridge import VisionContextNeedsBridge
from modules.autonomy.services.needs_engine import CompanionNeedsEngine


def test_vision_bridge_new_object_boosts_curiosity_context():
    bridge = VisionContextNeedsBridge({"ttl_s": 60})
    out = bridge.observe({"new_object": True, "summary": "new object"}, now=100.0)
    assert out["available"] is True
    assert out["reason"] == "vision.new_object"
    ctx = bridge.context(now=101.0)
    assert ctx["available"] is True
    assert ctx["scene"]["new_object"] is True
    assert ctx["mood_overrides"]["curiosity"] >= 80


def test_vision_bridge_person_sets_owner_present():
    bridge = VisionContextNeedsBridge({"ttl_s": 60})
    bridge.observe({"person_seen": True, "owner_present": True}, now=200.0)
    ctx = bridge.context(now=201.0)
    assert ctx["owner_present"] is True
    assert ctx["scene"]["person_seen"] is True


def test_vision_bridge_stale_context_is_not_available():
    bridge = VisionContextNeedsBridge({"ttl_s": 1})
    bridge.observe({"new_object": True}, now=10.0)
    ctx = bridge.context(now=20.0)
    assert ctx["available"] is False


def test_needs_engine_vision_new_object_recommends_exploration_or_curiosity():
    engine = CompanionNeedsEngine({"boredom_threshold_s": 100})
    out = engine.tick(
        now=100.0,
        last_interaction_ts=95.0,
        mood_state={"energy": 90, "curiosity": 50},
        needs_state={"stimulation": 40},
        scene={"new_object": True},
    )
    assert out["scores"]["curiosity"] >= 80
    assert out["recommended_goal"] in {"look_around_and_learn", "inspect_environment"}


def test_needs_engine_hazard_overrides_to_safety():
    engine = CompanionNeedsEngine({})
    out = engine.tick(
        now=100.0,
        last_interaction_ts=0.0,
        mood_state={"energy": 90, "curiosity": 90},
        needs_state={"stimulation": 90},
        scene={"hazards": ["obstacle"]},
    )
    assert out["dominant_need"] == "safety"
    assert out["recommended_goal"] == "pause_and_observe"
