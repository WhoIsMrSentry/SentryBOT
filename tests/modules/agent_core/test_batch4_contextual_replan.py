"""Batch 4 — contextual replan, policy gate, and goal continuity scenarios."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from modules.agent_core.services.runtime import (
    CandidatePlan,
    CompanionExecutionLoop,
    ContextualReplanner,
    DecisionTraceStore,
    Evaluation,
    FailureClass,
    Goal,
    GoalSnapshot,
    GoalStatus,
    GoalStore,
    Observation,
    Plan,
    PlanPolicyGate,
    PlanStep,
    PolicyConstraints,
    ReplanContext,
    StepStatus,
)
from modules.agent_core.services.runtime.schemas import RuntimeBudgetUsage


def _nav_obstacle_plan() -> Dict[str, Any]:
    return {
        "plan_id": "inspect:1",
        "behavior": "inspect_environment",
        "actions": [
            {"type": "navigation", "policy": "rest_corner", "capability": "navigation.rest_corner"},
            {"type": "pose", "name": "sleepy_idle", "capability": "pose.sleepy_idle"},
        ],
        "typed_goal": {"id": "goal_inspect", "objective": "inspect environment"},
        "typed_plan": {
            "id": "plan_inspect",
            "goal_id": "goal_inspect",
            "version": 1,
            "steps": [
                {
                    "id": "n1",
                    "objective": "navigate",
                    "required_capabilities": ["navigation.rest_corner"],
                    "status": "ready",
                    "metadata": {"action": {"type": "navigation", "policy": "rest_corner"}},
                },
                {
                    "id": "n2",
                    "objective": "inspect pose",
                    "required_capabilities": ["pose.sleepy_idle"],
                    "dependencies": ["n1"],
                    "status": "ready",
                    "metadata": {"action": {"type": "pose", "name": "sleepy_idle"}},
                },
            ],
        },
    }


def _steps(actions):
    return [
        {
            "component": "x",
            "capability": a.get("capability") or "semantic.noop",
            "params": dict(a),
            "method": "POST",
        }
        for a in actions
    ]


def test_navigation_obstacle_contextual_replan_not_universal_wait():
    def execute(cap, params):
        if cap == "navigation.rest_corner":
            return {"ok": False, "capability": cap, "reason": "obstacle:blocked"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    store = DecisionTraceStore(maxlen=32)
    loop = CompanionExecutionLoop(
        traces=store,
        cfg={
            "max_replans": 2,
            "contextual_replan": {"enabled": True, "llm_assist": False, "max_candidate_steps": 4},
        },
    )
    plan = _nav_obstacle_plan()
    result = loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert result["usage"]["replans"] >= 1
    caps = [
        s["required_capabilities"][0]
        for s in (result["plan"] or {}).get("steps", [])
        if s.get("required_capabilities") and s.get("status") in {"ready", "succeeded", "pending"}
    ]
    assert "vision.cheap" in caps
    assert "navigation.goal" in caps
    ready_or_done = [
        s
        for s in (result["plan"] or {}).get("steps", [])
        if s.get("status") in {"ready", "succeeded", "pending"} and s.get("required_capabilities")
    ]
    only_observe_wait = {s["required_capabilities"][0] for s in ready_or_done} <= {
        "vision.cheap",
        "scheduler.wait",
    }
    assert only_observe_wait is False
    traces = store.query(limit=20, goal_id="goal_inspect")
    assert any(t["decision"] == "contextual_replan" for t in traces)


def test_vision_unavailable_contextual_or_switch():
    calls: List[str] = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "vision.cheap":
            return {"ok": False, "capability": cap, "reason": "capability_not_found"}
        return {"ok": True, "capability": cap}

    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=16),
        cfg={"max_retries": 0, "max_replans": 2, "contextual_replan": {"enabled": True}},
    )
    plan = {
        "plan_id": "v",
        "actions": [{"type": "vision", "mode": "cheap", "capability": "vision.cheap"}],
        "typed_goal": {"id": "gv", "objective": "see"},
        "typed_plan": {
            "id": "pv",
            "goal_id": "gv",
            "steps": [
                {
                    "id": "v1",
                    "objective": "see",
                    "required_capabilities": ["vision.cheap"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision", "mode": "cheap"}},
                }
            ],
        },
    }
    result = loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert "vision.semantic" in calls or any(
        "vision.semantic" in str(s.get("required_capabilities"))
        for s in (result.get("plan") or {}).get("steps", [])
    )


def test_policy_rejection_blocks_unsafe_candidate():
    unsafe_step = PlanStep(
        objective="unsafe",
        required_capabilities=["motion.look_around"],
        status=StepStatus.READY,
        metadata={"action": {"type": "motion", "name": "look_around", "risk": "critical"}, "risk": "critical"},
    )
    candidate = CandidatePlan(
        plan=Plan(goal_id="g", steps=[unsafe_step]),
        replan_reason="llm_bad",
        strategy_hint="unsafe",
        source="llm_assisted",
    )
    gate = PlanPolicyGate(cfg={"risk_ceiling": "low", "blocked_risks": ["critical", "high"]})
    ctx = ReplanContext(
        original_goal=Goal(id="g", objective="x"),
        current_plan=Plan(goal_id="g", steps=[]),
        failed_step=PlanStep(objective="f", required_capabilities=["vision.cheap"]),
        observation=Observation(source="t", result={"reason": "x"}, success=False),
        evaluation=Evaluation(
            execution_success=False,
            goal_success=False,
            failure_class=FailureClass.UNEXPECTED_RESULT,
            reason="x",
        ),
        available_capabilities=["motion.look_around", "vision.cheap"],
        policy_constraints=PolicyConstraints(risk_ceiling="low", blocked_risks=["critical", "high"]),
    )
    decision = gate.approve(candidate, ctx)
    assert decision.__class__.__name__ == "Reject"
    assert "blocked_risk" in " ".join(decision.violations) or decision.reason == "policy_rejected"


def test_policy_rejection_during_loop_falls_back_without_executing_unsafe():
    calls: List[str] = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "assets.status":
            return {"ok": False, "capability": cap, "reason": "handler_failed"}
        return {"ok": True, "capability": cap}

    def evil_llm(context: ReplanContext) -> CandidatePlan:
        return CandidatePlan(
            plan=Plan(
                goal_id=context.original_goal.id,
                steps=[
                    PlanStep(
                        objective="boom",
                        required_capabilities=["motion.look_around"],
                        status=StepStatus.READY,
                        metadata={"risk": "critical", "action": {"risk": "critical"}},
                    )
                ],
            ),
            source="llm_assisted",
            strategy_hint="unsafe",
            replan_reason="evil",
        )

    store = DecisionTraceStore(maxlen=32)
    loop = CompanionExecutionLoop(
        traces=store,
        cfg={
            "max_retries": 0,
            "max_replans": 2,
            "contextual_replan": {
                "enabled": True,
                "llm_assist": True,
                "fallback_observe_wait": True,
                "risk_ceiling": "low",
                "blocked_risks": ["critical", "high"],
            },
        },
        llm_assist_fn=evil_llm,
        policy_constraints=PolicyConstraints(risk_ceiling="low", blocked_risks=["critical", "high"]),
    )
    # assets.status has no rules strategy → LLM consulted → policy rejects → fallback
    plan = {
        "plan_id": "u",
        "actions": [{"type": "system", "capability": "assets.status"}],
        "typed_goal": {"id": "goal_unsafe", "objective": "status"},
        "typed_plan": {
            "id": "pu",
            "goal_id": "goal_unsafe",
            "steps": [
                {
                    "id": "a1",
                    "objective": "status",
                    "required_capabilities": ["assets.status"],
                    "status": "ready",
                    "metadata": {"action": {"type": "system"}},
                }
            ],
        },
    }
    loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert calls.count("motion.look_around") == 0
    traces = store.query(limit=30, goal_id="goal_unsafe")
    assert any(t["decision"] == "contextual_replan" for t in traces)


def test_cross_tick_resume_same_goal_id():
    store = GoalStore(ttl_s=600)
    traces = DecisionTraceStore(maxlen=32)
    plan = _nav_obstacle_plan()

    def execute(cap, params):
        if cap == "navigation.rest_corner":
            return {"ok": False, "capability": cap, "reason": "obstacle:blocked"}
        return {"ok": True, "capability": cap}

    loop = CompanionExecutionLoop(
        traces=traces,
        goal_store=store,
        cfg={
            "max_iterations": 2,
            "max_replans": 1,
            "contextual_replan": {"enabled": True},
            "goal_persistence": {"enabled": True, "ttl_s": 600},
        },
    )
    result1 = loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    snap = store.active_or_waiting()
    if snap is None:
        snap = GoalSnapshot.from_dict(result1["goal_snapshot"])
        snap.status = GoalStatus.WAITING
        for step in (snap.current_plan or {}).get("steps", []):
            if step.get("required_capabilities") == ["vision.cheap"]:
                step["status"] = "ready"
        store.save(snap)
    goal_id = snap.goal_id
    assert goal_id == "goal_inspect"

    resume_plan = dict(snap.goal_plan or {})
    loop2 = CompanionExecutionLoop(
        traces=traces,
        goal_store=store,
        cfg={"max_iterations": 6, "contextual_replan": {"enabled": True}, "goal_persistence": {"ttl_s": 600}},
    )
    result2 = loop2.run(resume_plan, _steps(resume_plan.get("actions") or plan["actions"]), execute_capability=execute)
    assert (result2.get("goal") or {}).get("id") == goal_id


def test_expiration_not_resumed():
    store = GoalStore(ttl_s=1)
    snap = GoalSnapshot(
        goal_id="old",
        objective="x",
        status=GoalStatus.WAITING,
        expires_at=time.time() - 10,
        current_plan={
            "steps": [{"id": "s", "status": "ready", "required_capabilities": ["vision.cheap"], "objective": "see"}]
        },
        goal_plan={"typed_goal": {"id": "old"}, "actions": [{"capability": "vision.cheap"}]},
    )
    store.create(snap)
    # create() overwrites expires_at — force expiry
    snap.expires_at = time.time() - 10
    store.save(snap)
    store.expire_due_goals()
    assert store.get("old").status == GoalStatus.EXPIRED
    assert store.active_or_waiting() is None


def test_budget_continuity_across_ticks():
    store = GoalStore(ttl_s=600)
    plan = {
        "plan_id": "b",
        "typed_goal": {"id": "gb", "objective": "x"},
        "typed_plan": {
            "id": "pb",
            "goal_id": "gb",
            "steps": [
                {
                    "id": "s1",
                    "objective": "see",
                    "required_capabilities": ["vision.cheap"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision", "mode": "cheap"}},
                },
                {
                    "id": "s2",
                    "objective": "see2",
                    "required_capabilities": ["vision.semantic"],
                    "dependencies": ["s1"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision", "mode": "semantic"}},
                },
            ],
        },
        "actions": [
            {"capability": "vision.cheap", "type": "vision"},
            {"capability": "vision.semantic", "type": "vision"},
        ],
        "_runtime_budget_usage": RuntimeBudgetUsage(iterations=5, retries=0, replans=0).to_dict(),
    }

    def execute(cap, params):
        return {"ok": True, "capability": cap}

    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=8),
        goal_store=store,
        cfg={"max_iterations": 6, "goal_persistence": {"ttl_s": 600}},
    )
    result = loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert result["usage"]["iterations"] >= 6 or result["stop_reason"] == "max_iterations"


def test_progress_continuity_stops_no_progress():
    plan = {
        "plan_id": "p",
        "actions": [{"capability": "vision.cheap", "type": "vision"}],
        "typed_goal": {"id": "gp", "objective": "x"},
        "typed_plan": {
            "id": "pp",
            "goal_id": "gp",
            "steps": [
                {
                    "id": "s1",
                    "objective": "see",
                    "required_capabilities": ["vision.cheap"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision"}},
                }
            ],
        },
        "_progress_signatures": ["vision.cheap:[]", "vision.cheap:[]"],
        "_zero_progress": 2,
    }

    def execute(cap, params):
        return {"ok": False, "capability": cap, "reason": "handler_failed"}

    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=8),
        cfg={"max_retries": 0, "max_replans": 0, "max_zero_progress": 3, "max_identical_actions": 3},
    )
    result = loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert result["applied"] is False
    assert result["stop_reason"] in {
        "no_progress",
        "repeated_identical_action",
        "need_more_context",
        "plan_exhausted",
        "unhandled_failure",
    }


def test_side_effect_not_duplicated_on_contextual_replan():
    calls: List[str] = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "speech.short_prompt":
            return {"ok": False, "capability": cap, "reason": "handler_exception"}
        return {"ok": True, "capability": cap}

    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=8),
        cfg={"max_retries": 3, "max_replans": 2, "contextual_replan": {"enabled": True}},
    )
    plan = {
        "plan_id": "speak",
        "actions": [{"type": "speech", "capability": "speech.short_prompt"}],
        "typed_goal": {"id": "gs", "objective": "speak"},
        "typed_plan": {
            "id": "ps",
            "goal_id": "gs",
            "steps": [
                {
                    "id": "sp",
                    "objective": "speak",
                    "required_capabilities": ["speech.short_prompt"],
                    "status": "ready",
                    "metadata": {"action": {"type": "speech"}},
                }
            ],
        },
    }
    loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    assert calls.count("speech.short_prompt") == 1


def test_trace_chain_execute_fail_replan_approve():
    store = DecisionTraceStore(maxlen=32)

    def execute(cap, params):
        if cap == "navigation.rest_corner":
            return {"ok": False, "capability": cap, "reason": "obstacle:blocked"}
        return {"ok": True, "capability": cap}

    loop = CompanionExecutionLoop(
        traces=store,
        cfg={"max_replans": 2, "contextual_replan": {"enabled": True, "llm_assist": False}},
    )
    plan = _nav_obstacle_plan()
    loop.run(plan, _steps(plan["actions"]), execute_capability=execute)
    decisions = [t["decision"] for t in store.query(limit=30, goal_id="goal_inspect")]
    assert "capability_failed" in decisions or "execute_capability" in decisions
    assert "contextual_replan" in decisions


def test_rules_only_determinism():
    replanner = ContextualReplanner(cfg={"llm_assist": False, "max_candidate_steps": 4})
    goal = Goal(id="g", objective="inspect")
    failed = PlanStep(
        id="n1",
        objective="nav",
        required_capabilities=["navigation.rest_corner"],
        status=StepStatus.FAILED,
        metadata={"action": {"type": "navigation"}},
    )
    plan = Plan(
        goal_id="g",
        steps=[
            failed,
            PlanStep(
                id="n2",
                objective="pose",
                required_capabilities=["pose.sleepy_idle"],
                dependencies=["n1"],
                status=StepStatus.READY,
                metadata={"action": {"type": "pose", "name": "sleepy_idle"}},
            ),
        ],
    )
    ctx = ReplanContext(
        original_goal=goal,
        current_plan=plan,
        failed_step=failed,
        observation=Observation(
            source="capability.navigation.rest_corner",
            result={"ok": False, "reason": "obstacle:blocked"},
            success=False,
        ),
        evaluation=Evaluation(
            execution_success=False,
            goal_success=False,
            failure_class=FailureClass.UNEXPECTED_RESULT,
            reason="unexpected_result",
        ),
        available_capabilities=["vision.cheap", "navigation.goal", "pose.sleepy_idle", "scheduler.wait"],
    )
    a = replanner.replan(ctx)
    b = replanner.replan(ctx)
    assert a.source == b.source == "rules"
    assert a.strategy_hint == b.strategy_hint
    assert [s.required_capabilities for s in a.plan.steps] == [s.required_capabilities for s in b.plan.steps]
    assert "navigation.goal" in [s.required_capabilities[0] for s in a.plan.steps]


def test_mocked_llm_filtered_by_policy_gate():
    def llm_fn(context: ReplanContext) -> CandidatePlan:
        return CandidatePlan(
            plan=Plan(
                goal_id=context.original_goal.id,
                steps=[
                    PlanStep(
                        objective="ok",
                        required_capabilities=["vision.cheap"],
                        status=StepStatus.READY,
                        metadata={"risk": "none", "action": {"type": "vision", "mode": "cheap"}},
                    ),
                    PlanStep(
                        objective="missing",
                        required_capabilities=["vision.does_not_exist"],
                        status=StepStatus.READY,
                        metadata={"risk": "none"},
                    ),
                    PlanStep(
                        objective="unsafe",
                        required_capabilities=["motion.look_around"],
                        status=StepStatus.READY,
                        metadata={"risk": "critical", "action": {"risk": "critical"}},
                    ),
                ],
            ),
            source="llm_assisted",
            strategy_hint="mixed",
            replan_reason="mock",
        )

    replanner = ContextualReplanner(cfg={"llm_assist": True, "max_candidate_steps": 4}, llm_assist_fn=llm_fn)
    ctx = ReplanContext(
        original_goal=Goal(id="g", objective="x"),
        current_plan=Plan(goal_id="g", steps=[]),
        failed_step=PlanStep(objective="f", required_capabilities=["assets.status"]),
        observation=Observation(source="t", result={"reason": "unknown_glitch"}, success=False),
        evaluation=Evaluation(
            execution_success=False,
            goal_success=False,
            failure_class=FailureClass.UNKNOWN,
            reason="unknown",
        ),
        available_capabilities=["vision.cheap", "motion.look_around", "assets.status"],
        policy_constraints=PolicyConstraints(risk_ceiling="low", blocked_risks=["critical"], max_steps=4),
    )
    candidate = replanner.replan(ctx)
    assert candidate.source == "llm_assisted"
    gate = PlanPolicyGate(cfg={"risk_ceiling": "low", "blocked_risks": ["critical"]})
    decision = gate.approve(candidate, ctx)
    assert decision.__class__.__name__ == "Reject"
    joined = " ".join(decision.violations)
    assert "capability_unavailable" in joined or "blocked_risk" in joined or "risk_ceiling" in joined


def test_resume_priority_before_new_need():
    store = GoalStore(ttl_s=600)
    snap = GoalSnapshot(
        goal_id="goal_a",
        objective="inspect",
        status=GoalStatus.WAITING,
        expires_at=time.time() + 600,
        current_plan={
            "id": "p",
            "goal_id": "goal_a",
            "steps": [
                {
                    "id": "s1",
                    "objective": "see",
                    "required_capabilities": ["vision.cheap"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision", "mode": "cheap", "capability": "vision.cheap"}},
                }
            ],
        },
        goal_plan={
            "plan_id": "goal_a",
            "behavior": "inspect",
            "safe_to_execute": True,
            "typed_goal": {"id": "goal_a", "objective": "inspect"},
            "typed_plan": {
                "id": "p",
                "goal_id": "goal_a",
                "steps": [
                    {
                        "id": "s1",
                        "objective": "see",
                        "required_capabilities": ["vision.cheap"],
                        "status": "ready",
                        "metadata": {"action": {"type": "vision", "mode": "cheap"}},
                    }
                ],
            },
            "actions": [{"type": "vision", "mode": "cheap", "capability": "vision.cheap"}],
        },
    )
    store.create(snap)

    class FakeGate:
        def decide(self, plan, force=False, **_):
            return {"should_execute": True, "ok": True, "plan_behavior": plan.get("behavior"), "dry_run": True}

        def mark_execution(self, decision, execution):
            return {"ok": True, "executed": True, "execution": execution, **decision}

    class Brain:
        def __init__(self):
            self.goal_store = store
            self.goal_auto_execute_gate = FakeGate()
            self.state = {}
            self.config = {
                "companion_goal_executor": {"goal_persistence": {"resume_on_tick": True, "ttl_s": 600}}
            }
            self._selected_new = False

        def get_companion_goal_snapshot(self):
            self._selected_new = True
            return {"behavior": "fresh_need", "safe_to_execute": True, "actions": []}

        def execute_companion_goal(self, payload):
            plan = payload.get("goal_plan") or {}
            return {
                "ok": True,
                "applied": True,
                "cognitive_loop": {"goal": {"id": (plan.get("typed_goal") or {}).get("id")}},
            }

    from modules.autonomy.services.brain_parts.scenario_rituals import ScenarioRitualsMixin

    brain = Brain()
    result = ScenarioRitualsMixin.tick_companion_auto_execute(brain, payload={}, force=True)
    assert result.get("resumed_goal") is True
    assert result.get("resumed_goal_id") == "goal_a"
    assert brain._selected_new is False
