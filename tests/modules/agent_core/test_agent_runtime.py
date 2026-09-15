"""Unit tests for AgentRuntime cognitive-loop building blocks."""

from __future__ import annotations

from modules.agent_core.services.runtime import (
    AgentRuntime,
    CapabilityIndex,
    FailureClass,
    FailureClassifier,
    Goal,
    ProgressTracker,
    RecoveryManager,
    RuntimeState,
)


def test_failure_classifier_patterns():
    clf = FailureClassifier()
    assert clf.classify(success=True) == FailureClass.NONE
    assert clf.classify(success=False, error="camera_unavailable") == FailureClass.TOOL_UNAVAILABLE
    assert clf.classify(success=False, error="permission denied by owner lock") == FailureClass.PERMISSION
    assert clf.classify(success=False, result="Error executing x: timeout") == FailureClass.TEMPORARY


def test_recovery_manager_strategies():
    mgr = RecoveryManager()
    retry = mgr.decide(FailureClass.TEMPORARY, attempt=0, max_retries=2)
    assert retry.should_retry is True

    switch = mgr.decide(
        FailureClass.TOOL_UNAVAILABLE,
        alternate_tools=["search_memory", "get_vision"],
    )
    assert switch.should_switch_tool is True
    assert switch.alternate_tool == "search_memory"

    abort = mgr.decide(FailureClass.BUDGET_EXCEEDED)
    assert abort.should_abort is True


def test_progress_tracker_detects_loops():
    tracker = ProgressTracker(max_identical=3, max_zero_progress=3)
    assert tracker.record("a", progressed=False) is None
    assert tracker.record("a", progressed=False) is None
    assert tracker.record("a", progressed=False) == "no_progress"

    tracker.reset()
    assert tracker.record("tool:x", progressed=True) is None
    assert tracker.record("tool:x", progressed=True) is None
    assert tracker.record("tool:x", progressed=True) == "repeated_identical_action"


def test_capability_index_selects_and_reports_gaps():
    index = CapabilityIndex(
        tool_capabilities={
            "get_vision": ["vision.cheap"],
            "describe_scene": ["vision.semantic"],
            "speak": ["speech.short_prompt"],
        },
        registry={
            "capabilities": {
                "vision.cheap": {"enabled": True, "risk": "none"},
                "vision.semantic": {"enabled": False, "risk": "none"},
                "motion.fly": {"enabled": True, "handler": "drone"},
            }
        },
    )
    tools = index.select_tools(["vision.cheap"], available_tools=["get_vision", "speak"])
    assert tools == ["get_vision"]

    gaps = index.capability_gap(
        ["motion.fly", "vision.semantic"],
        available_tools=["get_vision", "speak"],
    )
    reasons = {g["missing_capability"]: g["reason"] for g in gaps}
    assert reasons["motion.fly"] == "registry_capability_without_llm_tool"
    assert reasons["vision.semantic"] == "capability_disabled_in_registry"


def test_agent_runtime_completes_plan_with_tools():
    calls = []

    def executor(name, args):
        calls.append((name, dict(args)))
        if name == "get_vision":
            return {"people": 1, "ok": True}
        if name == "speak":
            return "ok spoken"
        return f"Error: unknown {name}"

    runtime = AgentRuntime(
        tool_executor=executor,
        capability_index=CapabilityIndex(
            tool_capabilities={
                "get_vision": ["vision.cheap"],
                "speak": ["speech.short_prompt"],
            }
        ),
        available_tools=["get_vision", "speak"],
    )
    goal = Goal(
        objective="Inspect scene and greet",
        success_criteria=[],
    )
    plan = runtime.create_simple_plan(
        goal,
        [
            {
                "objective": "Look around",
                "required_capabilities": ["vision.cheap"],
            },
            {
                "objective": "Say hello",
                "required_capabilities": ["speech.short_prompt"],
                "dependencies": [],
            },
        ],
    )
    # Make speak depend on vision step id
    plan.steps[1].dependencies = [plan.steps[0].id]

    result = runtime.run(goal, plan)
    assert result["state"] == RuntimeState.COMPLETED.value
    assert result["goal"]["status"] == "completed"
    assert [c[0] for c in calls] == ["get_vision", "speak"]
    assert len(result["traces"]) >= 2


def test_agent_runtime_recovers_by_switching_tool():
    calls = []

    def executor(name, args):
        calls.append(name)
        if name == "get_vision":
            return "Error: camera_unavailable"
        if name == "get_visual_context":
            return {"context": "room empty", "ok": True}
        return "Error: boom"

    runtime = AgentRuntime(
        tool_executor=executor,
        capability_index=CapabilityIndex(
            tool_capabilities={
                "get_vision": ["vision.cheap"],
                "get_visual_context": ["vision.cheap"],
            }
        ),
        available_tools=["get_vision", "get_visual_context"],
    )
    goal = Goal(objective="See environment")
    plan = runtime.create_simple_plan(
        goal,
        [
            {
                "objective": "Get vision",
                "required_capabilities": ["vision.cheap"],
                "preferred_tools": ["get_vision"],
            }
        ],
    )
    result = runtime.run(goal, plan)
    assert "get_vision" in calls
    assert "get_visual_context" in calls
    assert result["state"] == RuntimeState.COMPLETED.value
    assert result["recovery"] is not None
    assert result["recovery"]["strategy"] == "switch_tool"


def test_agent_runtime_reports_capability_gap():
    runtime = AgentRuntime(
        tool_executor=lambda n, a: "ok",
        capability_index=CapabilityIndex(tool_capabilities={"speak": ["speech.short_prompt"]}),
        available_tools=["speak"],
    )
    goal = Goal(objective="Fly")
    plan = runtime.create_simple_plan(
        goal,
        [{"objective": "Fly", "required_capabilities": ["motion.fly"]}],
    )
    result = runtime.run(goal, plan)
    assert result["state"] == RuntimeState.FAILED.value
    assert result["stop_reason"] == "aborted"
    assert any(g["missing_capability"] == "motion.fly" for g in result["capability_gaps"])


def test_agent_runtime_budget_stops_infinite_retries():
    def executor(name, args):
        return "Error: temporary timeout"

    runtime = AgentRuntime(
        tool_executor=executor,
        capability_index=CapabilityIndex(
            tool_capabilities={"get_sensor_data": ["system.inspect"]}
        ),
        available_tools=["get_sensor_data"],
    )
    runtime.budget.max_iterations = 4
    runtime.budget.max_retries = 1
    goal = Goal(objective="Read sensors")
    plan = runtime.create_simple_plan(
        goal,
        [
            {
                "objective": "Sensors",
                "required_capabilities": ["system.inspect"],
                "preferred_tools": ["get_sensor_data"],
            }
        ],
    )
    result = runtime.run(goal, plan)
    assert result["state"] in {
        RuntimeState.FAILED.value,
        RuntimeState.BUDGET_EXCEEDED.value,
    }
    assert result["goal"]["status"] == "failed"
