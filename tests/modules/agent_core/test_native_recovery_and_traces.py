"""Batch 2 — native history loop recovery + decision trace API."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.agent_core.api.core import get_core_router
from modules.agent_core.services.runtime import (
    CapabilityIndex,
    DecisionTraceStore,
    FailureClass,
    FailureClassifier,
    ProgressTracker,
    RecoveryManager,
)
from modules.agent_core.services.runtime.native_tool_recovery import NativeToolRecovery


def test_native_recovery_retries_read_only_temporary_failure():
    calls = []

    def execute(name, args):
        calls.append(name)
        return {"battery": 80}

    handler = NativeToolRecovery(
        classifier=FailureClassifier(),
        recovery=RecoveryManager(),
        capabilities=CapabilityIndex(
            tool_capabilities={"get_sensor_data": ["system.inspect"]},
            registry={},
        ),
        progress=ProgressTracker(max_identical=5, max_zero_progress=5),
        traces=DecisionTraceStore(maxlen=16),
        max_retries=1,
        goal_id="t1",
    )
    out, meta, stop = handler.handle(
        "get_sensor_data",
        {},
        "Error executing get_sensor_data: timeout",
        execute_fn=execute,
        available_tools=["get_sensor_data"],
        iteration=1,
    )
    assert stop is False
    assert meta["success"] is True
    assert meta["recovery"]["recovered_via"] == "retry"
    assert calls == ["get_sensor_data"]
    assert isinstance(out, dict)
    assert out["success"] is True


def test_native_recovery_switches_read_only_tool():
    calls = []

    def execute(name, args):
        calls.append(name)
        if name == "get_vision":
            return "Error: camera_unavailable"
        return {"ok": True, "people": 0}

    handler = NativeToolRecovery(
        capabilities=CapabilityIndex(
            tool_capabilities={
                "get_vision": ["vision.cheap"],
                "get_visual_context": ["vision.cheap"],
            },
            registry={},
        ),
        traces=DecisionTraceStore(maxlen=16),
        max_retries=0,
        goal_id="t2",
    )
    out, meta, stop = handler.handle(
        "get_vision",
        {},
        "Error: camera_unavailable",
        execute_fn=execute,
        available_tools=["get_vision", "get_visual_context"],
        iteration=1,
    )
    assert stop is False
    assert meta["success"] is True
    assert meta["recovery"]["recovered_via"] == "switch_tool"
    assert "get_visual_context" in calls
    assert out["success"] is True


def test_native_recovery_does_not_auto_retry_side_effect_tools():
    calls = []

    def execute(name, args):
        calls.append(name)
        return "ok"

    handler = NativeToolRecovery(
        capabilities=CapabilityIndex(tool_capabilities={"speak": ["speech.short_prompt"]}, registry={}),
        traces=DecisionTraceStore(maxlen=8),
        max_retries=2,
        goal_id="t3",
    )
    out, meta, stop = handler.handle(
        "speak",
        {"text": "hi"},
        "Error executing speak: timeout",
        execute_fn=execute,
        available_tools=["speak"],
        iteration=1,
    )
    assert calls == []  # no auto retry of speak
    assert meta["success"] is False
    assert meta["failure"]["type"] == FailureClass.TEMPORARY.value
    assert isinstance(out, dict)
    assert out["recovery"]["suggested_action"] in {"retry", "abort", "unknown_try_alternate", "no_recovery_path"}


def test_native_recovery_stops_on_no_progress():
    handler = NativeToolRecovery(
        capabilities=CapabilityIndex(tool_capabilities={"get_location": ["navigation.localize"]}, registry={}),
        progress=ProgressTracker(max_identical=2, max_zero_progress=2),
        traces=DecisionTraceStore(maxlen=8),
        max_retries=0,
        goal_id="t4",
    )

    def execute(name, args):
        return "Error: permanent"

    out1, _, stop1 = handler.handle(
        "get_location", {}, "Error: boom", execute_fn=execute, available_tools=["get_location"], iteration=1
    )
    out2, meta2, stop2 = handler.handle(
        "get_location", {}, "Error: boom", execute_fn=execute, available_tools=["get_location"], iteration=2
    )
    assert stop1 is False or stop2 is True
    assert stop2 is True
    assert meta2.get("stopped") in {"no_progress", "repeated_identical_action"}


def test_decision_trace_store_sanitizes_and_bounds():
    store = DecisionTraceStore(maxlen=3)
    for i in range(5):
        store.record(
            goal_id="g1" if i % 2 == 0 else "g2",
            decision="use_tool",
            reason="ok",
            tool="get_vision",
            metadata={"prompt": "SECRET", "capability": "vision.cheap", "api_key": "x"},
            evaluation={"execution_success": True},
            iteration=i,
        )
    assert len(store) == 3
    public = store.query(limit=10, goal_id="g1")
    assert public
    for item in public:
        assert "prompt" not in str(item)
        assert item["trace_id"]
        assert item["capability"] == "vision.cheap"
        assert "api_key" not in str(item)


def test_decision_traces_api_endpoint():
    agent = MagicMock()
    agent.is_busy = False
    store = DecisionTraceStore(maxlen=16)
    store.record(
        goal_id="native_turn",
        decision="tool_failed",
        reason="temporary",
        tool="get_vision",
        metadata={"capability": "vision.cheap", "recovery": {"suggested_action": "retry"}},
        evaluation={"execution_success": False, "failure_class": "temporary"},
    )
    agent.decision_traces = store
    agent.speech_arbiter = MagicMock()
    agent.config = {}
    agent.api_native_tools = False
    agent.status_interval_s = 1.0
    agent.route_preview = MagicMock(return_value={})

    app = FastAPI()
    app.include_router(get_core_router(agent), prefix="/agent")
    client = TestClient(app)
    res = client.get("/agent/decision-traces", params={"limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["count"] >= 1
    assert body["traces"][0]["tool"] == "get_vision"
    assert body["traces"][0]["outcome"] == "failure"
    latest = client.get("/agent/decision-traces/latest")
    assert latest.status_code == 200
    assert latest.json()["ok"] is True
