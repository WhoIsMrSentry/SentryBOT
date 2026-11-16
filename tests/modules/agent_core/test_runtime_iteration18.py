"""Iteration 18 unit & integration tests for modules/agent_core/services/runtime (Birim 30)."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.agent_core.api.core import get_core_router
from modules.agent_core.services.runtime import (
    AgentRuntime,
    Budget,
    CapabilityIndex,
    CompanionExecutionLoop,
    ContextualReplanner,
    DecisionTraceStore,
    Evaluation,
    FailureClass,
    Goal,
    GoalFormationContext,
    GoalFormationService,
    GoalPolicyGate,
    GoalSnapshot,
    GoalStatus,
    GoalStore,
    Observation,
    Plan,
    PlanPolicyGate,
    PlanStep,
    PolicyConstraints,
    StepStatus,
)
from modules.agent_core.services.runtime.schemas import GoalCandidate, RuntimeBudgetUsage


def test_goal_store_rlock_and_sqlite_persistence(tmp_path):
    db_file = tmp_path / "goals.sqlite3"
    store1 = GoalStore(ttl_s=600.0, backend="sqlite", db_path=db_file)
    try:
        snap = GoalSnapshot(
            goal_id="g-persist",
            objective="Check room",
            status=GoalStatus.WAITING,
            current_plan={
                "steps": [
                    {
                        "id": "s1",
                        "objective": "look",
                        "status": "ready",
                        "required_capabilities": ["vision.cheap"],
                    }
                ]
            },
            goal_plan={"typed_goal": {"id": "g-persist", "objective": "Check room"}, "actions": [{"capability": "vision.cheap"}]},
        )
        store1.create(snap)
        store1.save(snap)

        # Concurrent multi-threaded Stress on GoalStore
        errors = []

        def _worker(idx: int) -> None:
            try:
                for step in range(15):
                    g = GoalSnapshot(goal_id=f"thr-{idx}-{step}", objective="t", status=GoalStatus.WAITING)
                    store1.create(g)
                    store1.active_or_waiting()
                    store1.status_summary()
                    store1.mark_status(g.goal_id, GoalStatus.COMPLETED)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
    finally:
        store1.close()

    # Reopen from SQLite and verify durable WAITING goal survives restart
    store2 = GoalStore(ttl_s=600.0, backend="sqlite", db_path=db_file)
    try:
        loaded = store2.get("g-persist")
        assert loaded is not None
        assert loaded.status == GoalStatus.WAITING
        active = store2.active_or_waiting()
        assert active is not None and active.goal_id == "g-persist"
    finally:
        store2.close()


def test_agent_runtime_invokes_contextual_replanner_and_policy_gate():
    cap_index = CapabilityIndex(
        tool_capabilities={
            "get_vision": ["vision.cheap"],
            "describe_scene": ["vision.semantic"],
            "stop_follow": ["motion.stop"],
        },
        registry={
            "capabilities": {
                "vision.cheap": {"enabled": True, "risk": "none"},
                "vision.semantic": {"enabled": True, "risk": "low"},
                "motion.stop": {"enabled": True, "risk": "none"},
            }
        },
    )
    calls = []

    def executor(tool_name, args):
        calls.append(tool_name)
        if tool_name == "get_vision":
            return "Error: unavailable"
        return "Scene: clear"

    def evaluate(goal, candidate, obs):
        ok = obs.success
        return Evaluation(
            execution_success=ok,
            goal_success=ok,
            should_replan=not ok,
            reason="ok" if ok else "invalid_plan",
            failure_class=FailureClass.NONE if ok else FailureClass.INVALID_PLAN,
        )

    runtime = AgentRuntime(
        tool_executor=executor,
        capability_index=cap_index,
        budget=Budget(max_iterations=6, max_retries=0, max_replans=2),
        evaluate_fn=evaluate,
        available_tools=["get_vision", "describe_scene"],
        replanner=ContextualReplanner(capabilities=cap_index, cfg={"enabled": True}),
        policy_gate=PlanPolicyGate(capabilities=cap_index, cfg={"risk_ceiling": "medium"}),
        policy_constraints=PolicyConstraints(risk_ceiling="medium", max_steps=4),
    )
    goal = Goal(id="g-replan", objective="Inspect room")
    plan = runtime.create_simple_plan(
        goal,
        [{"id": "s1", "objective": "vision", "required_capabilities": ["vision.cheap"], "preferred_tools": ["get_vision"]}],
    )
    snap = runtime.run(goal, plan)
    assert snap["usage"]["replans"] >= 1
    traces = runtime.traces.query(limit=20, goal_id="g-replan")
    assert any(t["decision"] == "contextual_replan" for t in traces)


def test_companion_loop_failed_retry_and_switch_do_not_report_true():
    loop = CompanionExecutionLoop(
        traces=DecisionTraceStore(maxlen=16),
        cfg={"max_retries": 1, "max_replans": 0, "contextual_replan": {"enabled": False}},
    )
    goal = Goal(id="gf", objective="check")
    step = PlanStep(id="s1", objective="see", required_capabilities=["vision.cheap"], status=StepStatus.FAILED)
    plan = Plan(goal_id="gf", steps=[step])
    obs = Observation(source="capability.vision.cheap", result={"ok": False}, success=False, action_id="s1")
    ev = Evaluation(execution_success=False, goal_success=False, should_replan=False, failure_class=FailureClass.TEMPORARY)

    rec_retry = SimpleNamespace(
        should_abort=False, should_retry=True, should_switch_tool=False, alternate_tool="", should_replan=False, should_ask_user=False, reason="temp"
    )
    out_retry = loop._apply_recovery(
        rec_retry,
        goal=goal,
        plan=plan,
        failed_step=step,
        failure=FailureClass.TEMPORARY,
        capability="vision.cheap",
        params={},
        observation=obs,
        evaluation=ev,
        execute_capability=lambda *_a: {"ok": False, "reason": "still_down"},
        step_results=[],
        observations=[],
    )
    assert out_retry["retried"] is False

    rec_switch = SimpleNamespace(
        should_abort=False, should_retry=False, should_switch_tool=True, alternate_tool="vision.semantic", should_replan=False, should_ask_user=False, reason="unavail"
    )
    out_switch = loop._apply_recovery(
        rec_switch,
        goal=goal,
        plan=plan,
        failed_step=step,
        failure=FailureClass.TOOL_UNAVAILABLE,
        capability="vision.cheap",
        params={},
        observation=obs,
        evaluation=ev,
        execute_capability=lambda *_a: {"ok": False, "reason": "alt_failed"},
        step_results=[],
        observations=[],
    )
    assert out_switch["switched"] is False


def test_runtime_budget_usage_tracks_active_time_across_waiting_pause(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("modules.agent_core.services.runtime.schemas.time.time", lambda: clock["now"])

    budget = Budget(max_iterations=6, max_retries=2, max_replans=2, max_execution_time_s=5.0)
    usage = RuntimeBudgetUsage()
    usage.begin_active(now=clock["now"])
    clock["now"] += 1.2
    usage.pause_active(now=clock["now"])
    serialized = usage.to_dict()

    # Sleep for 120 seconds while goal stays WAITING in GoalStore
    clock["now"] += 120.0
    resumed = RuntimeBudgetUsage.from_dict(serialized)
    assert resumed.exceeded(budget, now=clock["now"]) is None
    resumed.begin_active(now=clock["now"])
    clock["now"] += 1.0
    assert abs(resumed.elapsed_active(now=clock["now"]) - 2.2) < 0.05
    assert resumed.exceeded(budget, now=clock["now"]) is None

    # Active execution past remaining budget triggers max_execution_time
    clock["now"] += 3.5
    assert resumed.exceeded(budget, now=clock["now"]) == "max_execution_time"


def test_decision_trace_and_goal_formation_thread_safety_and_jsonl_rotation(tmp_path):
    log_file = tmp_path / "traces.jsonl"
    store = DecisionTraceStore(maxlen=32, log_path=log_file, max_bytes=1200, backup_count=2)
    errors = []

    def _trace_worker(tid: int) -> None:
        try:
            for i in range(25):
                store.record(
                    goal_id=f"g-{tid}",
                    decision="contextual_replan" if i % 5 == 0 else "execute",
                    reason=f"reason-{i}",
                    tool="get_vision",
                    metadata={"secret": "MUST_STRIP", "capability": "vision.cheap"},
                )
                store.query(limit=10)
                store.recent(5)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_trace_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert log_file.exists()
    # Rotating backups created due to compact max_bytes=1200
    assert (tmp_path / "traces.jsonl.1").exists()
    sample = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])
    assert "secret" not in json.dumps(sample)
    assert store.latest_replan() is not None

    # GoalFormationService thread safety
    gfs = GoalFormationService(traces=store)
    gf_errors = []

    def _form_worker() -> None:
        try:
            for _ in range(10):
                gfs.form({"needs": {"social": 0.7}, "dominant_need": "social", "owner_present": True}, now=time.time())
                gfs.last_decision()
        except Exception as exc:
            gf_errors.append(exc)

    gf_threads = [threading.Thread(target=_form_worker) for _ in range(3)]
    for t in gf_threads:
        t.start()
    for t in gf_threads:
        t.join()
    assert not gf_errors


def test_capability_index_prefix_risk_ranking_and_goal_policy_gate_no_describe(monkeypatch):
    # ask_vlm_about_scene is alphabetically BEFORE get_vision,
    # but get_vision (vision.cheap -> risk="none") MUST win over medium risk!
    idx = CapabilityIndex(
        tool_capabilities={
            "ask_vlm_about_scene": ["vision.semantic"],
            "get_vision": ["vision.cheap"],
        },
        registry={
            "capabilities": {
                "vision.cheap": {"enabled": True, "risk": "none"},
                "vision.semantic": {"enabled": True, "risk": "medium"},
            }
        },
    )
    selected = idx.select_tools(["vision"])
    assert selected == ["get_vision"]

    # GoalPolicyGate.approve must not repeatedly allocate via describe()
    describe_calls = {"n": 0}
    orig_describe = idx.describe

    def _spy_describe():
        describe_calls["n"] += 1
        return orig_describe()

    monkeypatch.setattr(idx, "describe", _spy_describe)
    gate = GoalPolicyGate(capabilities=idx)
    cand = GoalCandidate(intent="look_around_and_learn", required_capabilities=["vision.cheap", "vision.semantic"])
    ctx = GoalFormationContext(available_capabilities=["vision.cheap", "vision.semantic"])
    res = gate.approve(cand, ctx)
    assert res.reason == "approved"
    assert describe_calls["n"] == 0


def test_api_goals_status_endpoint():
    store = GoalStore(ttl_s=600.0)
    store.create(GoalSnapshot(goal_id="g-api", objective="Scan shelf", status=GoalStatus.WAITING))
    traces = DecisionTraceStore(maxlen=16)
    traces.record(goal_id="g-api", decision="contextual_replan", reason="path_blocked_alternate", tool="vision.semantic")

    app = FastAPI()
    stub_agent = SimpleNamespace(is_busy=False, goal_store=store, decision_traces=traces)
    app.include_router(get_core_router(stub_agent), prefix="/agent")

    client = TestClient(app)
    res = client.get("/agent/goals/status")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["available"] is True
    assert body["total"] == 1
    assert body["counts"]["waiting"] == 1
    assert body["active_goal"]["goal_id"] == "g-api"
    assert body["latest_replan"]["reason"] == "path_blocked_alternate"
