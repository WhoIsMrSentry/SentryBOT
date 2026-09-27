from modules.autonomy.services.companion_goal_selector import CompanionGoalSelector


def test_goal_selector_maps_exploration_to_safe_plan():
    selector = CompanionGoalSelector({"event_cooldown_s": 10})
    plan = selector.select(
        {
            "dominant_need": "exploration",
            "recommended_goal": "look_around_and_learn",
            "confidence": 0.8,
            "scores": {"exploration": 82, "energy": 90},
        },
        now=100.0,
    )
    assert plan["ok"] is True
    assert plan["behavior"] == "look_around_and_learn"
    assert plan["expression_event"] == "needs.exploration"
    assert plan["auto_execute"] is True
    assert any(a["type"] == "vision" for a in plan["actions"])


def test_goal_selector_event_cooldown():
    selector = CompanionGoalSelector({"event_cooldown_s": 10})
    first = selector.select({"dominant_need": "curiosity", "recommended_goal": "inspect_environment"}, now=100.0)
    second = selector.select({"dominant_need": "curiosity", "recommended_goal": "inspect_environment"}, now=105.0)
    third = selector.select({"dominant_need": "curiosity", "recommended_goal": "inspect_environment"}, now=111.0)
    assert first["event"] == "goal.curiosity"
    assert second["event"] == ""
    assert third["event"] == "goal.curiosity"


def test_goal_selector_safety_is_critical():
    selector = CompanionGoalSelector()
    plan = selector.select({"dominant_need": "safety", "recommended_goal": "pause_and_observe", "confidence": 0.9})
    assert plan["priority"] == "critical"
    assert plan["safe_to_execute"] is True
    assert plan["expression_event"] == "needs.safety"


def test_fresh_laya_urgency_supersedes_goal_with_safe_observation():
    selector = CompanionGoalSelector({
        "auto_execute": False,
        "goal_formation": {"enabled": False},
        "laya_urgency": {"enabled": True, "freshness_s": 8.0, "safety_score_floor": 0.75},
    })
    plan = selector.select(
        {
            "dominant_need": "social",
            "recommended_goal": "social_check_in",
            "scores": {"social": 0.9, "safety": 0.1},
            "laya_urgency": {"high": True, "score": 1.8, "timestamp": 96.0},
        },
        now=100.0,
    )

    assert plan["dominant_need"] == "safety"
    assert plan["recommended_goal"] == "pause_and_observe"
    assert plan["laya_urgency_override"] == {"score": 1.8, "age_s": 4.0}


def test_expired_laya_urgency_does_not_supersede_goal():
    selector = CompanionGoalSelector({
        "auto_execute": False,
        "goal_formation": {"enabled": False},
        "laya_urgency": {"enabled": True, "freshness_s": 8.0, "safety_score_floor": 0.75},
    })
    plan = selector.select(
        {
            "dominant_need": "social",
            "recommended_goal": "social_check_in",
            "scores": {"social": 0.9, "safety": 0.1},
            "laya_urgency": {"high": True, "score": 1.8, "timestamp": 80.0},
        },
        now=100.0,
    )

    assert plan["dominant_need"] == "social"
    assert plan["recommended_goal"] == "social_check_in"
    assert plan["laya_urgency_override"] is None
