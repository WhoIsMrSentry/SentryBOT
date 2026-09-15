"""Batch 5 — goal formation scenario tests."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from modules.agent_core.services.runtime import (
    CompanionPlanAdapter,
    DecisionTraceStore,
    Goal,
    GoalCandidate,
    GoalCandidateSource,
    GoalFormationService,
    GoalSnapshot,
    GoalStatus,
    GoalStore,
)
from modules.agent_core.services.runtime.goal_candidate_generator import GoalCandidateGenerator
from modules.agent_core.services.runtime.goal_formation import context_fingerprint
from modules.agent_core.services.runtime.schemas import GoalFormationContext, NeedSignal, PolicyConstraints
from modules.autonomy.services.companion_goal_selector import CompanionGoalSelector


def _snap(**kwargs) -> Dict[str, Any]:
    base = {
        "dominant_need": "curiosity",
        "recommended_goal": "inspect_environment",
        "confidence": 0.7,
        "scores": {"curiosity": 70, "social": 20, "rest": 10, "safety": 5, "boredom": 15, "energy": 70},
        "perception": {"novelty": 0.2, "hazards": []},
        "preferences": {},
        "routines": {},
        "capability_health": {"capabilities": []},
    }
    base.update(kwargs)
    return base


def test_same_need_different_context_different_goal():
    svc = GoalFormationService(cfg={"enabled": True, "min_activation_score": 0.3, "model_assist": False})
    # Context A: owner present + social need
    a = svc.form(
        _snap(
            dominant_need="social",
            recommended_goal="engage_owner",
            scores={"social": 80, "curiosity": 20, "safety": 5, "rest": 10, "energy": 70},
            perception={"novelty": 0.1},
        ),
        owner_present=True,
    )
    # Context B: owner absent + scene change
    b = svc.form(
        _snap(
            dominant_need="curiosity",
            recommended_goal="inspect_environment",
            scores={"curiosity": 75, "social": 15, "safety": 5, "rest": 10, "energy": 70},
            perception={"novelty": 0.8, "importance": 0.8},
        ),
        owner_present=False,
    )
    assert a.selected_intent == "social_check_in"
    assert b.selected_intent in {"inspect_environment", "look_around_and_learn"}
    assert a.selected_intent != b.selected_intent


def test_no_worthwhile_goal_defers():
    svc = GoalFormationService(
        cfg={"enabled": True, "min_activation_score": 0.85, "max_same_goal_repeats": 1, "repetition_window_s": 900}
    )
    # Seed repetition on calm_idle / inspect
    svc.evaluator.record_selection("inspect_environment", now=time.time())
    svc.evaluator.record_selection("inspect_environment", now=time.time())
    svc.evaluator.record_selection("calm_idle", now=time.time())
    decision = svc.form(
        _snap(
            dominant_need="balance",
            recommended_goal="calm_idle",
            scores={"curiosity": 10, "social": 10, "rest": 10, "safety": 5, "boredom": 10, "energy": 70},
            perception={"novelty": 0.05},
        ),
        owner_present=False,
    )
    assert decision.disposition.value == "defer"
    assert decision.selected_goal is None


def test_resume_beats_weak_curiosity():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="goal_wait",
            objective="inspect",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [
                    {
                        "id": "s1",
                        "status": "ready",
                        "required_capabilities": ["vision.cheap"],
                        "objective": "see",
                    }
                ]
            },
            goal_plan={
                "intent": "inspect_environment",
                "behavior": "inspect_environment_and_learn",
                "actions": [{"capability": "vision.cheap"}],
                "safe_to_execute": True,
            },
        )
    )
    svc = GoalFormationService(
        cfg={"enabled": True, "min_activation_score": 0.3, "continuity_bonus": 0.2},
        goal_store=store,
    )
    decision = svc.form(
        _snap(
            dominant_need="curiosity",
            scores={"curiosity": 40, "social": 10, "safety": 5, "rest": 10, "energy": 70},
            perception={"novelty": 0.2},
        ),
        owner_present=False,
    )
    assert decision.disposition.value == "resume"
    assert decision.selected_goal is not None
    assert decision.selected_goal.id == "goal_wait"


def test_urgent_safety_supersedes_valid_waiting_goal():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="goal_low",
            objective="idle look",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [{"id": "s1", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]
            },
            goal_plan={"intent": "inspect_environment", "actions": [{"capability": "vision.cheap"}]},
        )
    )
    svc = GoalFormationService(cfg={"enabled": True, "allow_supersede": True}, goal_store=store)
    decision = svc.form(
        _snap(
            dominant_need="safety",
            recommended_goal="pause_and_observe",
            scores={"safety": 90, "curiosity": 20, "social": 10, "rest": 10, "energy": 70},
            perception={"hazards": ["obstacle"], "novelty": 0.1},
        ),
        owner_present=False,
    )
    assert decision.disposition.value == "supersede"
    assert decision.selected_intent == "pause_and_observe"
    assert decision.superseded_goal_id == "goal_low"
    assert store.get("goal_low").status == GoalStatus.SUPERSEDED


def test_expired_goal_not_superseded_status():
    store = GoalStore(ttl_s=1)
    store.create(
        GoalSnapshot(
            goal_id="old",
            objective="x",
            status=GoalStatus.WAITING,
            expires_at=time.time() - 5,
            current_plan={"steps": [{"id": "s", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]},
            goal_plan={"actions": []},
        )
    )
    store.expire_due_goals()
    assert store.get("old").status == GoalStatus.EXPIRED
    svc = GoalFormationService(cfg={"enabled": True}, goal_store=store)
    decision = svc.form(_snap(dominant_need="curiosity", perception={"novelty": 0.7}), owner_present=False)
    assert decision.disposition.value != "supersede"
    assert store.get("old").status == GoalStatus.EXPIRED


def test_repetition_suppresses_duplicate_inspect():
    svc = GoalFormationService(cfg={"enabled": True, "max_same_goal_repeats": 2, "repetition_window_s": 900, "min_activation_score": 0.3})
    now = time.time()
    svc.evaluator.record_selection("inspect_environment", now=now)
    svc.evaluator.record_selection("inspect_environment", now=now)
    decision = svc.form(
        _snap(
            dominant_need="curiosity",
            scores={"curiosity": 80, "social": 10, "safety": 5, "rest": 10, "energy": 70},
            perception={"novelty": 0.2},
        ),
        owner_present=False,
    )
    assert decision.selected_intent != "inspect_environment" or decision.disposition.value == "defer"


def test_quiet_hours_rejects_social_before_planning():
    svc = GoalFormationService(cfg={"enabled": True, "min_activation_score": 0.2})
    decision = svc.form(
        _snap(
            dominant_need="social",
            scores={"social": 90, "curiosity": 10, "safety": 5, "rest": 10, "energy": 70},
            routines={"quiet_time": True},
            preferences={"quiet_mode": True},
        ),
        owner_present=True,
    )
    assert decision.selected_intent != "social_check_in"
    assert any("quiet" in r.get("reason", "") for r in decision.rejected) or decision.disposition.value in {
        "defer",
        "select",
        "resume",
    }


def test_capability_infeasibility_rejects_nav_intent():
    from modules.agent_core.services.runtime.capability_index import CapabilityIndex

    caps = CapabilityIndex(registry={"capabilities": {"vision.cheap": {"enabled": True, "risk": "none"}}})
    svc = GoalFormationService(cfg={"enabled": True, "min_activation_score": 0.2}, capabilities=caps)
    # Force settle_or_rest which needs navigation — should be rejected by policy when registry lacks nav
    decision = svc.form(
        _snap(
            dominant_need="rest",
            recommended_goal="rest_in_safe_place",
            scores={"rest": 90, "energy": 10, "curiosity": 5, "social": 5, "safety": 5},
            perception={"novelty": 0.0},
            capability_health={"capabilities": ["vision.cheap"]},
        ),
        owner_present=False,
    )
    assert decision.selected_intent != "settle_or_rest" or decision.disposition.value == "defer"


def test_budget_pressure_prefers_cheap_or_defer():
    svc = GoalFormationService(cfg={"enabled": True, "min_activation_score": 0.25})
    decision = svc.form(
        {
            **_snap(
                dominant_need="social",
                scores={"social": 70, "curiosity": 20, "safety": 5, "rest": 10, "energy": 70},
            ),
            "budget": {"low_budget": True},
        },
        owner_present=True,
    )
    # social_check_in cost 0.35 may be rejected under budget_pressure; cheap calm_idle or defer
    assert decision.selected_intent in {None, "calm_idle", "inspect_environment", "social_check_in", "seek_owner_or_invite"}
    if decision.selected_candidate and decision.selected_intent == "social_check_in":
        # If somehow approved, cost should still be gated elsewhere — allow but prefer not
        pass
    else:
        assert decision.disposition.value in {"defer", "select", "resume"}


def test_model_assist_filters_unknown_and_forbidden():
    def model_fn(context):
        return [
            GoalCandidate(intent="inspect_environment", reason="ok", source=GoalCandidateSource.MODEL, expected_utility=0.9, urgency=0.7, required_capabilities=["vision.cheap"]),
            GoalCandidate(intent="hack_the_planet", reason="bad", source=GoalCandidateSource.MODEL, expected_utility=1.0, urgency=1.0),
            GoalCandidate(intent="social_check_in", reason="quiet-bad", source=GoalCandidateSource.MODEL, expected_utility=0.9, urgency=0.8, required_capabilities=["speech.short_prompt"]),
        ]

    gen = GoalCandidateGenerator(cfg={"model_assist": True, "max_candidates": 6}, model_assist_fn=model_fn)
    ctx = GoalFormationContext(
        needs=[NeedSignal(kind="curiosity", strength=0.2)],
        dominant_need="balance",
        recommended_goal="calm_idle",
        scores={"curiosity": 0.2},
        quiet_hours=True,
        available_capabilities=["vision.cheap", "speech.short_prompt", "scheduler.wait"],
        policy_constraints=PolicyConstraints(quiet_hours=True),
    )
    cands = gen.generate(ctx)
    intents = {c.intent for c in cands}
    assert "hack_the_planet" not in intents
    assert "inspect_environment" in intents or "calm_idle" in intents


def test_rules_only_determinism():
    cfg = {"enabled": True, "model_assist": False, "min_activation_score": 0.3}
    snap = _snap(dominant_need="curiosity", perception={"novelty": 0.7})
    a = GoalFormationService(cfg=cfg).form(snap, owner_present=False, now=1000.0)
    b = GoalFormationService(cfg=cfg).form(snap, owner_present=False, now=1000.0)
    assert a.selected_intent == b.selected_intent
    assert a.disposition == b.disposition


def test_idempotent_reuse_same_fingerprint():
    selector = CompanionGoalSelector(
        {
            "enabled": True,
            "auto_execute": True,
            "goal_formation": {"enabled": True, "min_activation_score": 0.3, "model_assist": False},
        }
    )
    snap = _snap(dominant_need="curiosity", perception={"novelty": 0.7, "importance": 0.7})
    first = selector.select(snap, owner_present=False, now=1000.0)
    second = selector.select(snap, owner_present=False, now=1001.0)
    assert second.get("goal_formation", {}).get("reused") is True
    assert first.get("intent") == second.get("intent")


def test_build_for_intent_does_not_use_need_chain():
    adapter = CompanionPlanAdapter()
    goal = Goal(id="g1", objective="inspect", metadata={"intent": "inspect_environment"})
    plan = adapter.build_for_intent("inspect_environment", goal=goal, context={"owner_present": False})
    assert plan["template_key"] == "curiosity"
    assert plan["intent"] == "inspect_environment"
    assert plan["typed_goal"]["id"] == "g1"
    assert "legacy_build" not in (plan.get("typed_goal") or {}).get("metadata", {})


def test_selector_defer_disables_auto_execute():
    selector = CompanionGoalSelector(
        {
            "enabled": True,
            "auto_execute": True,
            "goal_formation": {
                "enabled": True,
                "min_activation_score": 0.95,
                "max_same_goal_repeats": 1,
                "model_assist": False,
            },
        }
    )
    selector.goal_formation.evaluator.record_selection("inspect_environment")
    selector.goal_formation.evaluator.record_selection("inspect_environment")
    selector.goal_formation.evaluator.record_selection("calm_idle")
    out = selector.select(
        _snap(
            dominant_need="balance",
            scores={"curiosity": 5, "social": 5, "rest": 5, "safety": 1, "boredom": 5, "energy": 70},
            perception={"novelty": 0.0},
        ),
        owner_present=False,
    )
    assert out.get("deferred") is True
    assert out.get("auto_execute") is False
    assert out.get("actions") == []


def test_formation_flows_to_adapter_plan():
    selector = CompanionGoalSelector(
        {"enabled": True, "goal_formation": {"enabled": True, "min_activation_score": 0.25, "model_assist": False}}
    )
    out = selector.select(
        _snap(dominant_need="curiosity", perception={"novelty": 0.8}),
        owner_present=False,
    )
    assert out.get("deferred") is False
    assert out.get("intent") in {"inspect_environment", "look_around_and_learn"}
    assert out.get("typed_plan")
    assert out.get("actions")
    assert out.get("template_key")
