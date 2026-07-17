from __future__ import annotations

import ast
from pathlib import Path

from modules.vlm_bridge.services.inference_budget import (
    VLM_INFERENCE_BUDGET_GATE_CONTRACT,
    VLM_INFERENCE_BUDGET_GATE_ROLE,
    VLM_INFERENCE_BUDGET_GATE_STATUS_ONLY_SAFE,
    VLMInferenceBudgetGate,
    build_vlm_inference_budget_gate,
)


SOURCE_PATH = Path("modules/vlm_bridge/services/inference_budget.py")


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def test_budget_gate_defaults_to_disabled_and_status_only_safe():
    gate = build_vlm_inference_budget_gate()
    decision = gate.check(now=10.0)

    assert VLM_INFERENCE_BUDGET_GATE_CONTRACT is True
    assert VLM_INFERENCE_BUDGET_GATE_ROLE == "pre_inference_rate_budget_and_circuit_gate"
    assert VLM_INFERENCE_BUDGET_GATE_STATUS_ONLY_SAFE is True
    assert decision.allowed is False
    assert decision.reason == "disabled"
    assert gate.status(now=10.0)["activation_started"] is False


def test_budget_gate_reserve_enforces_cooldown_without_inference():
    gate = VLMInferenceBudgetGate(enabled=True, max_requests_per_minute=2, min_interval_s=5.0)
    first = gate.reserve(now=100.0)
    second = gate.reserve(now=101.0)
    third = gate.reserve(now=106.0)

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "cooldown"
    assert second.retry_after_s == 4.0
    assert third.allowed is True


def test_budget_gate_enforces_rate_and_cost_budget():
    gate = VLMInferenceBudgetGate(
        enabled=True,
        max_requests_per_minute=2,
        max_cost_units_per_minute=2.0,
        min_interval_s=0.0,
    )
    assert gate.reserve(cost_units=1.5, now=1.0).allowed is True
    assert gate.reserve(cost_units=1.0, now=2.0).allowed is False
    assert gate.check(cost_units=1.0, now=2.0).reason == "cost_budget_exhausted"


def test_budget_gate_circuit_breaker_after_failures():
    gate = VLMInferenceBudgetGate(enabled=True, max_consecutive_failures=2, min_interval_s=0.0)
    gate.record_failure()
    assert gate.check(now=1.0).allowed is True
    gate.record_failure()
    decision = gate.check(now=2.0)
    assert decision.allowed is False
    assert decision.reason == "circuit_open_after_failures"
    gate.record_success()
    assert gate.check(now=3.0).allowed is True


def test_budget_gate_source_has_no_executable_camera_network_or_inference_start():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_import_roots = {"cv2", "requests", "httpx", "ollama"}
    imports = []
    calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                if root in forbidden_import_roots:
                    imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0].lower()
            if root in forbidden_import_roots:
                imports.append((node.module, node.lineno))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {"VideoCapture"}:
                    calls.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                root = _root_name(node.func.value)
                attr = node.func.attr
                if root == "cv2" and attr == "VideoCapture":
                    calls.append((f"{root}.{attr}", node.lineno))
                if root in {"requests", "httpx"} and attr in {"get", "post", "request", "send"}:
                    calls.append((f"{root}.{attr}", node.lineno))
                if root == "ollama" and attr in {"generate", "chat"}:
                    calls.append((f"{root}.{attr}", node.lineno))

    assert imports == []
    assert calls == []

    forbidden_runtime_endpoints = [
        "/camera/start",
        "/camera/snap",
        "/camera/video",
        "/vlm/analyze",
        "/vlm/caption",
    ]
    for endpoint in forbidden_runtime_endpoints:
        assert endpoint not in source
