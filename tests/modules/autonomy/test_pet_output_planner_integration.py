from __future__ import annotations

from modules.autonomy.services.companion_behavior_loop import (
    PET_OUTPUT_PLANNER_BEHAVIOR_LOOP_INTEGRATION_CONTRACT,
    CompanionBehaviorLoop,
)
from modules.autonomy.services.pet_output_planner import (
    PET_OUTPUT_PLANNER_CONTRACT,
    PET_OUTPUT_PLANNER_HARDWARE_SAFE,
    PET_OUTPUT_PLANNER_ROLE,
    build_pet_output_plan,
)


def test_pet_output_planner_contract_markers():
    assert PET_OUTPUT_PLANNER_CONTRACT is True
    assert PET_OUTPUT_PLANNER_ROLE == "pet_intent_to_expression_motion_speech_semantic_plan"
    assert PET_OUTPUT_PLANNER_HARDWARE_SAFE is True


def test_attend_owner_maps_to_expression_motion_speech_semantics():
    plan = build_pet_output_plan(
        {
            "intent": "attend_owner",
            "expression_hint": "happy_attentive",
            "motion_hint": "orient_to_owner",
            "speech_hint": "short_warm",
        }
    )

    assert plan["intent"] == "attend_owner"
    assert plan["expression"]["name"] == "happy_attentive"
    assert plan["motion"]["name"] == "orient_to_owner"
    assert plan["speech"]["style"] == "short_warm"
    assert plan["speech"]["utterance"] == "BuradayÄ±m."
    assert plan["semantic_only"] is True
    assert plan["safety"]["hardware_enabled"] is False


def test_safe_observe_remains_low_amplitude_and_silent_safe():
    plan = build_pet_output_plan({"intent": "safe_observe"})

    assert plan["expression"]["name"] == "alert_soft"
    assert plan["motion"]["amplitude"] <= 0.05
    assert plan["motion"]["requires_arm_gate"] is True
    assert plan["safety"]["motion_started"] is False
    assert plan["safety"]["camera_started"] is False


def test_behavior_loop_builds_pet_output_plan_from_pet_companion():
    assert PET_OUTPUT_PLANNER_BEHAVIOR_LOOP_INTEGRATION_CONTRACT is True

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
    assert decision["pet_output_plan"]["intent"] == "attend_owner"
    assert decision["pet_output_plan"]["expression"]["name"] == "happy_attentive"
    assert decision["pet_expression_command"]["name"] == "happy_attentive"
    assert decision["pet_motion_command"]["name"] == "orient_to_owner"
    assert decision["pet_speech_command"]["style"] == "short_warm"
    assert decision["pet_output_plan"]["safety"]["hardware_enabled"] is False


def test_pet_output_plan_defaults_for_calm_idle():
    plan = build_pet_output_plan({})

    assert plan["intent"] == "calm_idle"
    assert plan["expression"]["name"] == "calm_alive"
    assert plan["motion"]["name"] == "breathing_idle"
    assert plan["speech"]["style"] == "silent"
    assert plan["speech"]["utterance"] == ""
