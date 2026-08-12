
from modules.autonomy.services.audio_event_needs_bridge import AudioEventNeedsBridge
from modules.autonomy.services.needs_engine import CompanionNeedsEngine


def test_audio_bridge_wakeword_sets_owner_context():
    bridge = AudioEventNeedsBridge({"ttl_s": 60})
    out = bridge.observe({"wakeword": True, "confidence": 0.9}, now=100.0)
    assert out["available"] is True
    assert out["reason"] == "audio.wakeword"
    ctx = bridge.context(now=101.0)
    assert ctx["available"] is True
    assert ctx["owner_present"] is True
    assert ctx["audio_context"]["wakeword"] is True
    assert ctx["needs_overrides"]["social"] >= 90


def test_audio_bridge_loud_sets_fear_override():
    bridge = AudioEventNeedsBridge({"ttl_s": 60})
    bridge.observe({"loud": True}, now=100.0)
    ctx = bridge.context(now=101.0)
    assert ctx["audio_context"]["loud"] is True
    assert ctx["mood_overrides"]["fear"] >= 50


def test_audio_bridge_stale_context_is_not_available():
    bridge = AudioEventNeedsBridge({"ttl_s": 1})
    bridge.observe({"sound": True}, now=10.0)
    ctx = bridge.context(now=20.0)
    assert ctx["available"] is False


def test_needs_engine_wakeword_can_select_social_goal():
    engine = CompanionNeedsEngine({"boredom_threshold_s": 100, "alone_threshold_s": 120})
    out = engine.tick(
        now=100.0,
        last_interaction_ts=98.0,
        mood_state={"energy": 95, "curiosity": 45},
        needs_state={"stimulation": 40},
        scene={"audio_context": {"wakeword": True}},
    )
    assert out["reasons"]["audio_context"]["wakeword"] is True
    assert out["dominant_need"] == "social"
    assert out["recommended_goal"] == "llm_behavior_planning"


def test_needs_engine_loud_audio_selects_safety_goal():
    engine = CompanionNeedsEngine({"boredom_threshold_s": 100})
    out = engine.tick(
        now=100.0,
        last_interaction_ts=98.0,
        mood_state={"energy": 95, "curiosity": 45},
        needs_state={"stimulation": 40},
        scene={"audio_context": {"loud": True}},
    )
    assert out["reasons"]["audio_context"]["loud"] is True
    assert out["dominant_need"] == "safety"
    assert out["recommended_goal"] == "pause_and_observe"
