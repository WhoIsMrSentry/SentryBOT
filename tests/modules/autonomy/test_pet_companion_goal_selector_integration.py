from __future__ import annotations

from modules.autonomy.services.companion_behavior_loop import (
    PET_COMPANION_BEHAVIOR_LOOP_INTEGRATION_CONTRACT,
    CompanionBehaviorLoop,
)
from modules.autonomy.services.companion_goal_selector import (
    PET_COMPANION_GOAL_SELECTOR_INTEGRATION_CONTRACT,
    CompanionGoalSelector,
)


def test_goal_selector_exports_pet_companion_integration_marker():
    assert PET_COMPANION_GOAL_SELECTOR_INTEGRATION_CONTRACT is True


def test_goal_selector_adds_pet_companion_side_channel_without_breaking_existing_behavior():
    selector = CompanionGoalSelector({"event_cooldown_s": 0.0})
    plan = selector.select(
        {
            "dominant_need": "social",
            "recommended_goal": "engage_owner",
            "confidence": 0.8,
            "scores": {"social": 0.8, "curiosity": 0.1, "boredom": 0.1, "safety": 0.0},
        },
        owner_present=True,
        now=10.0,
    )

    assert plan["behavior"] == "engage_owner"
    assert plan["pet_intent"] == "attend_owner"
    assert plan["pet_companion"]["intent"] == "attend_owner"
    assert plan["pet_companion"]["safety"]["hardware_enabled"] is False
    assert any(action.get("type") == "pet_intent" for action in plan["actions"])


def test_goal_selector_safety_context_produces_pet_safe_observe():
    selector = CompanionGoalSelector({"event_cooldown_s": 0.0})
    plan = selector.select(
        {
            "dominant_need": "safety",
            "recommended_goal": "pause",
            "confidence": 0.9,
            "scores": {"safety": 0.9, "social": 0.9, "curiosity": 0.9},
        },
        owner_present=True,
        now=11.0,
    )

    assert plan["priority"] == "critical"
    assert plan["pet_intent"] == "safe_observe"
    assert "prefer_safe_observation" in plan["pet_companion"]["goal_hints"]
    assert plan["pet_companion"]["safety"]["motion_started"] is False


def test_goal_selector_can_disable_pet_companion_integration():
    selector = CompanionGoalSelector({"pet_companion_enabled": False})
    plan = selector.select(
        {
            "dominant_need": "social",
            "recommended_goal": "engage_owner",
            "scores": {"social": 0.8},
        },
        owner_present=True,
        now=12.0,
    )

    assert plan["pet_companion"] == {}
    assert plan["pet_intent"] == ""


def test_behavior_loop_carries_pet_intent_and_hints():
    assert PET_COMPANION_BEHAVIOR_LOOP_INTEGRATION_CONTRACT is True

    loop = CompanionBehaviorLoop({"interval_s": 1.0, "min_idle_s": 0.0})
    decision = loop.decide(
        needs={"idle_s": 99.0},
        goal={
            "plan_id": "social:engage",
            "priority": "normal",
            "behavior": "engage_owner",
            "pet_intent": "attend_owner",
            "pet_companion": {
                "intent": "attend_owner",
                "expression_hint": "happy_attentive",
                "motion_hint": "orient_to_owner",
                "speech_hint": "short_warm",
            },
        },
        now=100.0,
        force=True,
    )

    assert decision["should_tick"] is True
    assert decision["pet_intent"] == "attend_owner"
    assert decision["pet_expression_hint"] == "happy_attentive"
    assert decision["pet_motion_hint"] == "orient_to_owner"
    assert decision["pet_speech_hint"] == "short_warm"
