"""Batch 2 — companion plan adapter + capability-driven typed plans."""

from __future__ import annotations

from modules.agent_core.services.runtime import (
    CapabilityIndex,
    CompanionPlanAdapter,
    select_template_key,
)
from modules.autonomy.services.companion_goal_selector import CompanionGoalSelector
from modules.autonomy.services.companion_goal_translator import CompanionGoalTranslatorMixin


def test_select_template_key_domain_policy():
    assert select_template_key("safety", "x", owner_present=False) == "safety"
    assert select_template_key("social", "x", owner_present=True) == "social_present"
    assert select_template_key("social", "x", owner_present=False) == "social_absent"
    assert select_template_key("exploration", "look_around_and_learn", owner_present=False) == "exploration"
    assert select_template_key("balance", "calm", owner_present=False) == "balance"


def test_adapter_builds_typed_plan_with_capabilities():
    index = CapabilityIndex(
        tool_capabilities={},
        registry={
            "capabilities": {
                "expression.event": {"enabled": True, "risk": "none"},
                "vision.cheap": {"enabled": True, "risk": "none"},
                "motion.look_around": {"enabled": True, "risk": "low"},
            }
        },
    )
    adapter = CompanionPlanAdapter(capability_index=index)
    out = adapter.build("exploration", "look_around_and_learn", owner_present=False)
    assert out["behavior"] == "look_around_and_learn"
    assert out["typed_plan"]["goal_id"]
    assert len(out["typed_plan"]["steps"]) >= 3
    caps = [s["required_capabilities"][0] for s in out["typed_plan"]["steps"] if s["required_capabilities"]]
    assert "vision.cheap" in caps
    assert "motion.look_around" in caps
    assert any(a["type"] == "vision" for a in out["actions"])
    assert any(a.get("capability") == "motion.look_around" or a.get("name") == "look_around" for a in out["actions"])


def test_adapter_skips_disabled_capability():
    index = CapabilityIndex(
        tool_capabilities={},
        registry={
            "capabilities": {
                "expression.event": {"enabled": True},
                "vision.cheap": {"enabled": True},
                "vision.semantic": {"enabled": False},
                "motion.attend": {"enabled": True},
            }
        },
    )
    adapter = CompanionPlanAdapter(capability_index=index)
    out = adapter.build("curiosity", "inspect_environment", owner_present=False)
    assert any(g["missing_capability"] == "vision.semantic" for g in out["capability_gaps"])
    assert all(
        not (a.get("mode") == "semantic") for a in out["actions"]
    ), "disabled semantic vision should not appear in executable actions"


def test_goal_selector_exposes_typed_plan():
    selector = CompanionGoalSelector(
        {
            "event_cooldown_s": 1,
            "pet_companion_enabled": False,
            "goal_formation": {"enabled": True, "min_activation_score": 0.25, "model_assist": False},
        }
    )
    plan = selector.select(
        {
            "dominant_need": "exploration",
            "recommended_goal": "look_around_and_learn",
            "confidence": 0.8,
            "scores": {"exploration": 82, "curiosity": 70, "safety": 5, "social": 10, "rest": 10, "energy": 70},
            "perception": {"novelty": 0.5},
        },
        now=100.0,
    )
    assert plan.get("deferred") is False
    assert plan.get("intent") == "look_around_and_learn"
    assert plan["behavior"] == "look_around_and_learn"
    assert isinstance(plan.get("typed_plan"), dict)
    assert plan["typed_plan"].get("steps")
    assert "template_key" in plan
    assert plan.get("goal_formation")


def test_translator_maps_perception_and_memory_and_navigation_name():
    step = CompanionGoalTranslatorMixin._translate_step(
        {"type": "perception", "name": "track_person", "label": "person"}
    )
    assert step["capability"] == "perception.track_object"

    mem = CompanionGoalTranslatorMixin._translate_step(
        {"type": "memory", "name": "observe", "summary": "x"}
    )
    assert mem["capability"] == "memory.observe"

    nav = CompanionGoalTranslatorMixin._translate_step(
        {"type": "navigation", "name": "rest_corner", "risk": "low"}
    )
    assert nav["capability"] == "navigation.rest_corner"
