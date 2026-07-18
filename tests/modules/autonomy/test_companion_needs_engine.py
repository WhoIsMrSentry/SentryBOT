from modules.autonomy.services.needs_engine import CompanionNeedsEngine


def test_needs_engine_detects_boredom_and_exploration():
    engine = CompanionNeedsEngine({"boredom_threshold_s": 10, "alone_threshold_s": 60})
    snap = engine.tick(
        now=100.0,
        last_interaction_ts=80.0,
        mood_state={"energy": 90, "curiosity": 80, "fear": 0},
        needs_state={"social": 30, "stimulation": 70, "rest": 80},
        owner_present=False,
        pc_test=True,
    )
    assert snap["ok"] is True
    assert snap["scores"]["boredom"] == 100.0
    assert snap["dominant_need"] in {"exploration", "boredom", "curiosity"}
    assert snap["recommended_goal"] in {"look_around_and_learn", "choose_idle_activity", "inspect_environment"}
    assert snap["event"].startswith("needs.")


def test_needs_engine_safety_wins_over_curiosity():
    engine = CompanionNeedsEngine({"boredom_threshold_s": 10})
    snap = engine.tick(
        now=200.0,
        last_interaction_ts=100.0,
        mood_state={"energy": 90, "curiosity": 95, "fear": 80},
        needs_state={"social": 80, "stimulation": 90, "rest": 80},
        scene={"hazards": ["edge"]},
        pc_test=False,
    )
    assert snap["dominant_need"] == "safety"
    assert snap["recommended_goal"] == "pause_and_observe"


def test_needs_engine_interaction_reduces_social_need_when_owner_present():
    engine = CompanionNeedsEngine({"alone_threshold_s": 60})
    engine.observe_interaction("speech")
    snap = engine.tick(
        now=20.0,
        last_interaction_ts=10.0,
        mood_state={"energy": 75, "curiosity": 45, "fear": 0},
        needs_state={"social": 10, "stimulation": 20, "rest": 80},
        owner_present=True,
        pc_test=True,
    )
    assert snap["scores"]["social"] < 15
    assert snap["reasons"]["last_interaction_source"] == "speech"


def test_needs_engine_snapshot_before_tick_is_safe():
    engine = CompanionNeedsEngine()
    snap = engine.snapshot()
    assert snap["ok"] is True
    assert snap["available"] is False