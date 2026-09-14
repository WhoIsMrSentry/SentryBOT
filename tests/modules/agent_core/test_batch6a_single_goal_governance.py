"""Batch 6a — single-goal governance refinement scenarios."""

from __future__ import annotations

import time

from modules.agent_core.services.runtime import (
    GoalFormationService,
    GoalSnapshot,
    GoalStatus,
    GoalStore,
)
from modules.agent_core.services.runtime.goal_evaluator import GoalEvaluator


def _snap(**kwargs):
    base = {
        "dominant_need": "curiosity",
        "recommended_goal": "inspect_environment",
        "confidence": 0.7,
        "scores": {"curiosity": 70, "social": 20, "rest": 10, "safety": 5, "boredom": 15, "energy": 70},
        "perception": {"novelty": 0.3, "hazards": []},
        "preferences": {},
        "routines": {},
    }
    base.update(kwargs)
    return base


def test_sticky_replanning_without_work_is_healed():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="stuck",
            objective="x",
            status=GoalStatus.REPLANNING,
            expires_at=time.time() + 600,
            current_plan={"steps": [{"id": "s", "status": "failed", "required_capabilities": ["vision.cheap"], "objective": "see"}]},
            goal_plan={"intent": "inspect_environment"},
        )
    )
    healed = store.heal_stuck_replanning()
    assert "stuck" in healed
    assert store.get("stuck").status == GoalStatus.FAILED
    assert store.active_or_waiting() is None


def test_replanning_with_work_becomes_waiting():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="mid",
            objective="x",
            status=GoalStatus.REPLANNING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [{"id": "s", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]
            },
            goal_plan={"intent": "inspect_environment", "actions": [{"capability": "vision.cheap"}]},
        )
    )
    store.heal_stuck_replanning()
    assert store.get("mid").status == GoalStatus.WAITING
    assert store.active_or_waiting() is not None


def test_cancel_marks_cancelled_and_prunes_old_terminals():
    store = GoalStore(ttl_s=600, max_terminal_keep=2, terminal_max_age_s=3600)
    for i in range(5):
        store.create(
            GoalSnapshot(
                goal_id=f"t{i}",
                objective="x",
                status=GoalStatus.COMPLETED,
                updated_at=time.time() - i,
                current_plan={"steps": []},
            )
        )
    removed = store.prune_terminals()
    assert removed >= 3
    assert len([s for s in store.all() if s.status == GoalStatus.COMPLETED]) <= 2
    store.create(
        GoalSnapshot(
            goal_id="live",
            objective="x",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            current_plan={"steps": [{"id": "s", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]},
        )
    )
    store.cancel("live", reason="soft_abandon")
    assert store.get("live").status == GoalStatus.CANCELLED
    assert store.get("live").metadata.get("cancel_reason") == "soft_abandon"


def test_outcome_failure_makes_intent_a_less_attractive_than_b():
    ev = GoalEvaluator(
        cfg={
            "min_activation_score": 0.1,
            "outcome_failure_penalty": 0.5,
            "continuity_bonus": 0.0,
            "max_same_goal_repeats": 10,
        }
    )
    from modules.agent_core.services.runtime import GoalCandidate, GoalFormationContext, NeedSignal

    ctx = GoalFormationContext(
        needs=[NeedSignal(kind="curiosity", strength=0.7)],
        dominant_need="curiosity",
        scores={"curiosity": 0.7, "social": 0.2},
        now=time.time(),
    )
    a = GoalCandidate(
        intent="inspect_environment",
        expected_utility=0.7,
        urgency=0.4,
        novelty=0.4,
        estimated_cost=0.3,
        estimated_risk=0.2,
    )
    b = GoalCandidate(
        intent="look_around_and_learn",
        expected_utility=0.65,
        urgency=0.35,
        novelty=0.35,
        estimated_cost=0.3,
        estimated_risk=0.2,
    )
    before, *_ = ev.evaluate([a, b], ctx)
    assert before is not None
    assert before.intent == "inspect_environment"
    # Fail intent A twice — outcome scoring alone must demote A below B
    ev.record_outcome("inspect_environment", succeeded=False, now=time.time())
    ev.record_outcome("inspect_environment", succeeded=False, now=time.time())
    score_a = ev._features(a, ctx, 0.0)
    score_b = ev._features(b, ctx, 0.0)
    assert score_a["outcome_adjustment"] < 0
    assert score_a["score"] < score_b["score"]
    after, *_rest = ev.evaluate([a, b], ctx)
    assert after is not None
    assert after.intent == "look_around_and_learn"


def test_soft_interrupt_owner_social_displaces_waiting_inspect():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="wait_inspect",
            objective="inspect",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [{"id": "s1", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]
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
        cfg={
            "enabled": True,
            "allow_supersede": True,
            "allow_soft_interrupt": True,
            "soft_interrupt_social_min": 0.55,
            "min_activation_score": 0.25,
            "continuity_bonus": 0.2,
        },
        goal_store=store,
    )
    decision = svc.form(
        _snap(
            dominant_need="social",
            recommended_goal="engage_owner",
            scores={"social": 85, "curiosity": 30, "safety": 5, "rest": 10, "energy": 70},
            perception={"novelty": 0.1},
        ),
        owner_present=True,
    )
    assert decision.disposition.value == "supersede"
    assert decision.selected_intent == "social_check_in"
    assert decision.superseded_goal_id == "wait_inspect"
    assert store.get("wait_inspect").status == GoalStatus.SUPERSEDED


def test_weak_curiosity_still_resumes_waiting_without_owner():
    store = GoalStore(ttl_s=600)
    store.create(
        GoalSnapshot(
            goal_id="wait_inspect",
            objective="inspect",
            status=GoalStatus.WAITING,
            expires_at=time.time() + 600,
            params={"intent": "inspect_environment"},
            current_plan={
                "steps": [{"id": "s1", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]
            },
            goal_plan={"intent": "inspect_environment", "actions": [{"capability": "vision.cheap"}]},
        )
    )
    svc = GoalFormationService(
        cfg={"enabled": True, "allow_soft_interrupt": True, "min_activation_score": 0.25},
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
    assert decision.selected_goal.id == "wait_inspect"


def test_safety_supersede_still_works():
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
            scores={"safety": 90, "curiosity": 20, "social": 10, "rest": 10, "energy": 70},
            perception={"hazards": ["obstacle"]},
        ),
        owner_present=False,
    )
    assert decision.disposition.value == "supersede"
    assert decision.selected_intent == "pause_and_observe"


def test_no_multi_goal_queue_introduced():
    store = GoalStore(ttl_s=600)
    assert not hasattr(store, "enqueue")
    assert not hasattr(store, "pending_queue")
    assert callable(store.active_or_waiting)
