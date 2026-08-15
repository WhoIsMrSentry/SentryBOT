from __future__ import annotations

import json

from modules.autonomy.services.topomap_motion_executor import TopomapMotionExecutor
from modules.autonomy.services.brain import AutonomyBrain
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


def test_goal_selector_uses_environmental_policy_for_variable_pet_intents():
    policy = {
        "enabled": True,
        "exploration_probability": 0.0,
        "exploration_band": 0.0,
        "safety_hold_threshold": 0.75,
        "signals": {
            "novelty": ["perception.novelty"],
            "curiosity": ["scores.curiosity"],
            "safety": ["scores.safety"],
        },
        "candidates": {
            "quiet_observation": {
                "base": 0.10,
                "behavior": "calm_idle",
                "recommended_goal": "inspect_environment_and_learn",
                "semantic": "quiet_observation",
                "weights": {"novelty": 0.10, "safety": -0.50},
            },
            "curious_scan": {
                "base": 0.05,
                "behavior": "curious_scan",
                "recommended_goal": "inspect_environment_and_learn",
                "semantic": "curious_scan",
                "weights": {"novelty": 0.60, "curiosity": 0.30, "safety": -0.80},
            },
        },
    }
    selector = CompanionGoalSelector({"environment_policy": policy})
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "scores": {"curiosity": 0.9, "safety": 0.1},
            "perception": {"novelty": 1.0},
        },
        now=100.0,
    )
    assert plan["environmental_choice"]["candidate"] == "curious_scan"
    assert plan["pet_expression_hint"] == "curious_scan"
    assert any(action.get("semantic") == "curious_scan" for action in plan["actions"])

    safety_plan = selector.select(
        {
            "dominant_need": "safety",
            "scores": {"curiosity": 0.9, "safety": 0.95},
            "perception": {"novelty": 1.0},
        },
        now=200.0,
    )
    assert safety_plan["environmental_choice"]["reason"] == "safety_hold"

def test_topomap_social_distance_policy_rejects_nearby_place(tmp_path):
    map_path = tmp_path / "topomap_places.json"
    map_path.write_text(
        json.dumps(
            {
                "places": [
                    {
                        "name": "nearby",
                        "tags": ["safe", "social_distance"],
                        "distance_from_owner_m": 0.4,
                        "steps": [{"type": "wait", "duration_s": 0.1}],
                    },
                    {
                        "name": "quiet_corner",
                        "tags": ["safe", "social_distance"],
                        "distance_from_owner_m": 1.8,
                        "steps": [{"type": "wait", "duration_s": 0.1}],
                    },
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    executor = TopomapMotionExecutor(
        {
            "map_path": str(map_path),
            "allow_base_motion": False,
            "companion_policies": {
                "social_distance": {
                    "enabled": True,
                    "required_tags": ["safe", "social_distance"],
                    "minimum_distance_from_owner_m": 1.2,
                    "selection": "random",
                }
            },
        }
    )
    result = executor.execute_companion_policy("social_distance")
    assert result["selected_place"] == "quiet_corner"
    assert result["policy"] == "social_distance"

def test_goal_selector_materializes_yaml_navigation_output():
    selector = CompanionGoalSelector(
        {
            "pet_companion_enabled": True,
            "environment_policy": {
                "enabled": True,
                "exploration_probability": 0.0,
                "exploration_band": 0.0,
                "safety_hold_threshold": 0.9,
                "signals": {},
                "candidates": {
                    "curious_scan": {
                        "base": 1.0,
                        "behavior": "curious_scan",
                        "recommended_goal": "inspect_environment_and_learn",
                        "semantic": "curious_scan",
                        "weights": {"curiosity": 1.0},
                        "outputs": [{"type": "navigation", "policy": "safe_exploration", "risk": "low"}],
                    }
                },
            },
        }
    )
    plan = selector.select(
        {"dominant_need": "curiosity", "scores": {"curiosity": 0.9, "safety": 0.1}},
        now=10.0,
    )
    assert {"type": "navigation", "policy": "safe_exploration", "risk": "low", "source": "environment_policy"} in plan["actions"]

def test_topomap_learning_requires_safe_tag_for_exploration(tmp_path):
    executor = TopomapMotionExecutor(
        {
            "map_path": str(tmp_path / "topomap_places.json"),
            "place_validation": {
                "allowed_tags": ["safe", "exploration", "social_distance"],
                "safe_required_for": ["exploration", "social_distance"],
                "distance_required_for": ["social_distance"],
                "motion_required_for": ["safe", "exploration", "social_distance"],
            },
        }
    )
    rejected = executor.learn_place(
        {
            "name": "unsafe_exploration",
            "tags": ["exploration"],
            "steps": [{"type": "wait", "duration_s": 0.1}],
        }
    )
    assert rejected["ok"] is False
    assert rejected["reason"] == "safe_tag_required"

def test_goal_selector_holds_motion_when_observation_confidence_is_low():
    selector = CompanionGoalSelector(
        {
            "event_cooldown_s": 0.0,
            "autonomy_policy": {
                "uncertainty": {
                    "enabled": True,
                    "confidence_paths": ["perception.confidence"],
                    "hold_below": 0.45,
                    "fallback_semantic": "quiet_observation",
                    "suppress_action_types": ["navigation", "motion"],
                    "reason": "low_observation_confidence",
                }
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "scores": {"curiosity": 0.9, "safety": 0.1},
            "perception": {"confidence": 0.2},
        },
        now=10.0,
    )
    assert plan["autonomy_guard"]["reason"] == "low_observation_confidence"
    assert plan["pet_expression_hint"] == "quiet_observation"
    assert any(action.get("semantic") == "quiet_observation" for action in plan["actions"])
    assert not any(action.get("type") in {"navigation", "motion"} for action in plan["actions"])

def test_goal_selector_applies_owner_quiet_preference():
    selector = CompanionGoalSelector(
        {
            "event_cooldown_s": 0.0,
            "autonomy_policy": {
                "personalization": {
                    "enabled": True,
                    "rules": [
                        {
                            "signal_paths": ["preferences.quiet_mode"],
                            "when": True,
                            "suppress_action_types": ["speech"],
                            "semantic": "quiet_observation",
                            "reason": "owner_prefers_quiet",
                        }
                    ],
                }
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "scores": {"curiosity": 0.9, "safety": 0.1},
            "preferences": {"quiet_mode": True},
        },
        now=10.0,
    )
    assert plan["personalization"][0]["reason"] == "owner_prefers_quiet"
    assert plan["pet_expression_hint"] == "quiet_observation"
    assert not any(action.get("type") == "speech" for action in plan["actions"])

def test_goal_selector_applies_privacy_guard_and_explanation():
    selector = CompanionGoalSelector(
        {
            "event_cooldown_s": 0.0,
            "autonomy_policy": {
                "privacy": {
                    "enabled": True,
                    "restricted_zone_paths": ["perception.zone"],
                    "restricted_zones": ["private"],
                    "guest_paths": ["perception.guest_present"],
                    "suppress_action_types": ["vision", "memory_write"],
                    "reason": "privacy_restricted_context",
                },
                "explanation": {
                    "enabled": True,
                    "include": ["privacy"],
                },
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "scores": {"curiosity": 0.9, "safety": 0.1},
            "perception": {"zone": "private"},
        },
        now=10.0,
    )
    assert plan["privacy"]["reason"] == "privacy_restricted_context"
    assert plan["decision_explanation"]["privacy"]["zones"] == ["private"]

def test_goal_selector_blocks_unavailable_capability_action():
    selector = CompanionGoalSelector(
        {
            "event_cooldown_s": 0.0,
            "autonomy_policy": {
                "capability_gate": {
                    "enabled": True,
                    "snapshot_path": "capability_health",
                    "default_required": {"navigation": ["navigation.goal"]},
                    "fallback_semantic": "quiet_observation",
                    "reason": "capability_unavailable",
                }
            },
            "environment_policy": {
                "enabled": True,
                "exploration_probability": 0.0,
                "exploration_band": 0.0,
                "safety_hold_threshold": 1.0,
                "signals": {"curiosity": ["scores.curiosity"]},
                "candidates": {
                    "curious_scan": {
                        "base": 1.0,
                        "behavior": "curious_scan",
                        "semantic": "curious_scan",
                        "weights": {"curiosity": 1.0},
                        "outputs": [{"type": "navigation", "policy": "safe_exploration"}],
                    }
                },
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "scores": {"curiosity": 0.9, "safety": 0.1},
            "capability_health": {
                "ok": True,
                "capabilities": {"navigation.goal": {"available": False}},
                "unavailable_components": [],
            },
        },
        now=10.0,
    )
    assert plan["capability_guard"]["reason"] == "capability_unavailable"
    assert not any(action.get("type") == "navigation" for action in plan["actions"])
    assert plan["pet_expression_hint"] == "quiet_observation"

def test_goal_selector_exposes_bounded_outcome_learning_feedback():
    selector = CompanionGoalSelector(
        {
            "enabled": True,
            "auto_execute": True,
            "outcome_learning": {
                "enabled": True,
                "max_weight_adjustment": 0.25,
                "safe_semantic": "quiet_observation",
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "recommended_goal": "calm_idle",
            "scores": {"curiosity": 0.6},
            "outcome_learning": {
                "candidate_weight_adjustments": {"curiosity": 2.0},
                "temporary_avoid_tags": [],
            },
        },
        now=10.0,
    )
    assert plan["outcome_learning"]["candidate_weight_adjustments"]["curiosity"] == 0.25
    assert plan["scores"]["curiosity"] == 0.8

def test_goal_selector_social_policy_blocks_multiple_people_motion():
    selector = CompanionGoalSelector(
        {
            "enabled": True,
            "auto_execute": True,
            "social_policy": {
                "enabled": True,
                "default_behavior": "observe_only",
                "safe_semantic": "quiet_observation",
                "person_types": {
                    "multiple_people": {
                        "auto_execute": False,
                        "restricted_action_types": ["motion", "navigation"],
                    },
                },
            },
        }
    )
    plan = selector.select(
        {
            "dominant_need": "curiosity",
            "recommended_goal": "calm_idle",
            "scores": {"curiosity": 0.8},
            "perception": {"people": [{"name": "a"}, {"name": "b"}]},
        },
        now=10.0,
    )
    assert plan["social_guard"]["person_type"] == "multiple_people"
    assert plan["auto_execute"] is False

def test_companion_replay_validates_ordered_expected_output():
    brain = object.__new__(AutonomyBrain)
    brain.state = {}
    brain.goal_selector = CompanionGoalSelector({"enabled": True, "auto_execute": False})
    result = brain.run_companion_e2e_scenario(
        {
            "timeline": [
                {
                    "timestamp": 1.0,
                    "needs": {
                        "dominant_need": "balance",
                        "recommended_goal": "calm_idle",
                        "scores": {"balance": 0.4},
                    },
                    "expected": {"recommended_goal": "calm_idle", "suppressed": True},
                }
            ]
        }
    )
    assert result["replay"] is True
    assert result["step_count"] == 1
    assert result["ok"] is True


def test_goal_selector_exposes_yaml_config_sources():
    selector = CompanionGoalSelector({"enabled": True})

    result = selector.select(
        {"dominant_need": "balance", "recommended_goal": "calm_idle", "scores": {}},
        owner_present=False,
        now=1.0,
    )

    assert result["config_source"]["root"] == "companion_goals"
    assert result["config_source"]["policies"] == {
        "uncertainty": "companion_goals.autonomy_policy.uncertainty",
        "personalization": "companion_goals.autonomy_policy.personalization",
        "privacy": "companion_goals.autonomy_policy.privacy",
        "explanation": "companion_goals.autonomy_policy.explanation",
        "capability_health": "companion_goals.autonomy_policy.health",
        "environment": "companion_goals.environment_policy",
        "outcome_learning": "outcome_learning",
        "social": "social_policy",
        "pet_companion": "companion_goals.pet_companion_enabled",
    }