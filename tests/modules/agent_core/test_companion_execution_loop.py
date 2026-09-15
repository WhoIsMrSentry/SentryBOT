"""Batch 3 — companion cognitive execution loop scenario tests."""

from __future__ import annotations

from typing import Any, Dict

from modules.agent_core.services.runtime import (
    CompanionExecutionLoop,
    DecisionTraceStore,
    FailureClass,
    Plan,
    PlanStep,
    StepStatus,
    observation_replan,
)
from modules.agent_core.services.runtime.companion_execution_loop import classify_capability_result
from modules.autonomy.services.companion_goal_executor import CompanionGoalExecutor


def _sample_typed_plan() -> Dict[str, Any]:
    return {
        "plan_id": "explore:1",
        "behavior": "look_around_and_learn",
        "dominant_need": "exploration",
        "safe_to_execute": True,
        "actions": [
            {"type": "expression", "event": "needs.exploration", "capability": "expression.event"},
            {"type": "vision", "mode": "cheap", "reason": "exploration", "capability": "vision.cheap"},
            {"type": "motion", "name": "look_around", "risk": "low", "capability": "motion.look_around"},
        ],
        "typed_goal": {
            "id": "goal_explore",
            "objective": "explore",
            "status": "pending",
        },
        "typed_plan": {
            "id": "plan_explore",
            "goal_id": "goal_explore",
            "version": 1,
            "steps": [
                {
                    "id": "s1",
                    "objective": "express",
                    "required_capabilities": ["expression.event"],
                    "status": "ready",
                    "metadata": {"action": {"type": "expression", "event": "needs.exploration"}},
                },
                {
                    "id": "s2",
                    "objective": "see",
                    "required_capabilities": ["vision.cheap"],
                    "dependencies": ["s1"],
                    "status": "ready",
                    "metadata": {"action": {"type": "vision", "mode": "cheap"}},
                },
                {
                    "id": "s3",
                    "objective": "move",
                    "required_capabilities": ["motion.look_around"],
                    "dependencies": ["s2"],
                    "status": "ready",
                    "metadata": {"action": {"type": "motion", "name": "look_around"}},
                },
            ],
        },
    }


def _steps_from_actions(actions):
    return [
        {
            "component": "x",
            "capability": a.get("capability") or "semantic.noop",
            "params": dict(a),
            "method": "POST",
        }
        for a in actions
    ]


def test_classify_capability_result():
    assert classify_capability_result({"ok": True}) == FailureClass.NONE
    assert classify_capability_result({"ok": False, "reason": "capability_not_found"}) == FailureClass.TOOL_UNAVAILABLE
    assert classify_capability_result({"ok": False, "reason": "risk_blocked:high"}) == FailureClass.UNSAFE_ACTION


def test_successful_multi_step_companion_goal():
    calls = []

    def execute(cap, params):
        calls.append(cap)
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=16))
    plan = _sample_typed_plan()
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["applied"] is True
    assert result["stop_reason"] == "completed"
    assert calls == ["expression.event", "vision.cheap", "motion.look_around"]
    assert len(result["observations"]) == 3
    assert result["usage"]["iterations"] >= 3


def test_temporary_vision_failure_retries_read_only():
    calls = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "vision.cheap" and calls.count("vision.cheap") == 1:
            return {"ok": False, "capability": cap, "reason": "handler_exception"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=16), cfg={"max_retries": 2})
    plan = _sample_typed_plan()
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["applied"] is True
    assert calls.count("vision.cheap") == 2
    assert result["usage"]["retries"] >= 1


def test_unavailable_vision_switches_to_semantic():
    calls = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "vision.cheap":
            return {"ok": False, "capability": cap, "reason": "capability_not_found"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=16), cfg={"max_retries": 0})
    plan = _sample_typed_plan()
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert "vision.semantic" in calls
    assert result["applied"] is True


def test_navigation_failure_replans_observe_and_wait():
    plan = {
        "plan_id": "nav:1",
        "behavior": "rest",
        "actions": [
            {"type": "navigation", "policy": "rest_corner", "capability": "navigation.rest_corner"},
            {"type": "pose", "name": "sleepy_idle", "capability": "pose.sleepy_idle"},
        ],
        "typed_goal": {"id": "g1", "objective": "rest"},
        "typed_plan": {
            "id": "p1",
            "goal_id": "g1",
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
                    "objective": "pose",
                    "required_capabilities": ["pose.sleepy_idle"],
                    "dependencies": ["n1"],
                    "status": "ready",
                    "metadata": {"action": {"type": "pose", "name": "sleepy_idle"}},
                },
            ],
        },
    }

    def execute(cap, params):
        if cap == "navigation.rest_corner":
            return {"ok": False, "capability": cap, "reason": "handler_failed"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=16), cfg={"max_replans": 2})
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["usage"]["replans"] >= 1
    updated = result["plan"]
    assert updated["metadata"].get("replanned") is True
    caps = [s["required_capabilities"][0] for s in updated["steps"] if s.get("required_capabilities")]
    assert "vision.cheap" in caps
    # Batch 4: contextual path prefers alternate navigation when available.
    assert ("navigation.goal" in caps) or ("scheduler.wait" in caps)


def test_repeated_identical_failure_stops_with_no_progress():
    def execute(cap, params):
        return {"ok": False, "capability": cap, "reason": "handler_failed"}

    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=8),
        cfg={"max_retries": 0, "max_replans": 0, "max_zero_progress": 2},
    )
    plan = {
        "plan_id": "fail",
        "actions": [{"type": "vision", "mode": "cheap", "capability": "vision.cheap"}],
    }
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["applied"] is False
    assert result["stop_reason"] in {"no_progress", "repeated_identical_action", "plan_exhausted", "unhandled_failure"}


def test_unsafe_action_aborts_without_retry():
    calls = []

    def execute(cap, params):
        calls.append(cap)
        return {"ok": False, "capability": cap, "reason": "risk_blocked:critical"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=8), cfg={"max_retries": 2})
    plan = {
        "plan_id": "unsafe",
        "actions": [{"type": "motion", "name": "look_around", "capability": "motion.look_around"}],
    }
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["applied"] is False
    assert calls.count("motion.look_around") == 1


def test_side_effect_speech_failure_not_auto_retried():
    calls = []

    def execute(cap, params):
        calls.append(cap)
        if cap == "speech.short_prompt":
            return {"ok": False, "capability": cap, "reason": "handler_exception"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=8), cfg={"max_retries": 3})
    plan = {
        "plan_id": "speak",
        "actions": [
            {"type": "expression", "event": "needs.social", "capability": "expression.event"},
            {"type": "speech", "mode": "short_prompt", "capability": "speech.short_prompt"},
        ],
    }
    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert calls.count("speech.short_prompt") == 1
    assert result["applied"] is False


def test_budget_exhaustion_stops_loop():
    loop = CompanionExecutionLoop(traces=DecisionTraceStore(maxlen=8), cfg={"max_iterations": 2})
    plan = _sample_typed_plan()

    def execute(cap, params):
        return {"ok": True, "capability": cap}

    result = loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    assert result["stop_reason"] == "max_iterations"
    assert result["applied"] is False


def test_observation_replan_skips_blocked_motion_steps():
    plan = Plan(
        goal_id="g",
        steps=[
            PlanStep(id="a", objective="nav", required_capabilities=["navigation.rest_corner"], status=StepStatus.READY),
            PlanStep(
                id="b",
                objective="pose",
                required_capabilities=["pose.sleepy_idle"],
                dependencies=["a"],
                status=StepStatus.READY,
            ),
        ],
    )
    failed = plan.steps[0]
    updated = observation_replan(plan, failed, FailureClass.UNEXPECTED_RESULT)
    assert updated is not None
    assert plan.steps[1].status == StepStatus.SKIPPED
    assert any(s.required_capabilities == ["vision.cheap"] for s in plan.steps[2:])


def test_traces_record_recovery_chain():
    store = DecisionTraceStore(maxlen=16)

    def execute(cap, params):
        if cap == "vision.cheap":
            return {"ok": False, "capability": cap, "reason": "handler_exception"}
        return {"ok": True, "capability": cap, "reason": "executed"}

    loop = CompanionExecutionLoop(traces=store, cfg={"max_retries": 1})
    plan = {
        "plan_id": "trace",
        "typed_goal": {"id": "tg", "objective": "x"},
        "typed_plan": {
            "id": "tp",
            "goal_id": "tg",
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
        "actions": [{"type": "vision", "mode": "cheap", "capability": "vision.cheap"}],
    }
    loop.run(plan, _steps_from_actions(plan["actions"]), execute_capability=execute)
    public = store.query(limit=10, goal_id="tg")
    assert len(public) >= 1
    assert any(t["tool"] == "vision.cheap" for t in public)


class _FakeCapabilityExecutor:
    def __init__(self, handler):
        self.handler = handler

    def execute(self, name, params):
        return self.handler(name, params)


class _FakeClient:
    pass


def test_executor_delegates_to_cognitive_loop_when_enabled():
    calls = []

    def handler(name, params):
        calls.append(name)
        return {"ok": True, "capability": name, "reason": "executed"}

    ex = CompanionGoalExecutor(
        {
            "enabled": True,
            "dry_run_default": False,
            "allow_real_hardware": True,
            "cognitive_loop": {"enabled": True, "max_retries": 1},
        },
        client=_FakeClient(),
    )
    ex.capabilities = _FakeCapabilityExecutor(handler)
    plan = _sample_typed_plan()
    result = ex.execute(plan, dry_run=False, pc_test=False)
    assert result["applied"] is True
    assert "cognitive_loop" in result
    assert result["cognitive_loop"]["observations"]
    assert calls
