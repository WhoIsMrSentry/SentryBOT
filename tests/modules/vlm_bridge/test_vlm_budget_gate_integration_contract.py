from __future__ import annotations

import ast
from pathlib import Path

from modules.vlm_bridge.services.budgeted_inference import (
    VLM_BUDGET_GATE_INTEGRATION_CONTRACT,
    VLM_BUDGET_GATE_INTEGRATION_DEFAULT_NO_INFERENCE,
    VLM_BUDGET_GATE_INTEGRATION_ROLE,
    BudgetedVLMExecutor,
    build_budgeted_vlm_executor,
)
from modules.vlm_bridge.services.inference_budget import VLMInferenceBudgetGate


SOURCE_PATH = Path("modules/vlm_bridge/services/budgeted_inference.py")


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def test_vlm_budget_gate_integration_contract_markers():
    assert VLM_BUDGET_GATE_INTEGRATION_CONTRACT is True
    assert VLM_BUDGET_GATE_INTEGRATION_ROLE == "budget_gate_required_before_vlm_callable"
    assert VLM_BUDGET_GATE_INTEGRATION_DEFAULT_NO_INFERENCE is True


def test_default_executor_denies_without_calling_inference():
    calls = []

    def fake_inference(payload):
        calls.append(payload)
        return {"ok": True}

    executor = BudgetedVLMExecutor(inference_callable=fake_inference)
    result = executor.run({"frame_ref": "already_captured_elsewhere"}, now=10.0).as_dict()

    assert result["allowed"] is False
    assert result["reason"] == "disabled"
    assert result["inference_called"] is False
    assert result["activation_started"] is False
    assert result["camera_started"] is False
    assert result["frame_captured"] is False
    assert result["hardware_enabled"] is False
    assert calls == []


def test_enabled_gate_calls_injected_callable_once_after_reserve():
    calls = []

    def fake_inference(payload):
        calls.append(payload)
        return {"caption": "safe semantic result"}

    gate = VLMInferenceBudgetGate(enabled=True, max_requests_per_minute=2, min_interval_s=0.0)
    executor = BudgetedVLMExecutor(gate=gate, inference_callable=fake_inference)

    result = executor.run({"context_id": "abc"}, now=20.0).as_dict()

    assert result["allowed"] is True
    assert result["reason"] == "inference_completed"
    assert result["inference_called"] is True
    assert result["result"] == {"caption": "safe semantic result"}
    assert calls == [{"context_id": "abc"}]


def test_budget_denial_prevents_callable_execution():
    calls = []

    def fake_inference(payload):
        calls.append(payload)
        return {"ok": True}

    gate = VLMInferenceBudgetGate(enabled=True, max_requests_per_minute=1, min_interval_s=0.0)
    executor = BudgetedVLMExecutor(gate=gate, inference_callable=fake_inference)

    first = executor.run({"n": 1}, now=1.0).as_dict()
    second = executor.run({"n": 2}, now=2.0).as_dict()

    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["reason"] == "request_budget_exhausted"
    assert calls == [{"n": 1}]


def test_missing_callable_is_safe_and_records_no_inference_call():
    gate = VLMInferenceBudgetGate(enabled=True, max_requests_per_minute=2, min_interval_s=0.0)
    executor = BudgetedVLMExecutor(gate=gate, inference_callable=None)

    result = executor.run({"context_id": "abc"}, now=30.0).as_dict()

    assert result["allowed"] is False
    assert result["reason"] == "inference_callable_missing"
    assert result["inference_called"] is False
    assert result["camera_started"] is False
    assert result["frame_captured"] is False


def test_builder_uses_disabled_budget_config_by_default():
    executor = build_budgeted_vlm_executor()
    result = executor.run({"x": 1}, now=40.0).as_dict()

    assert result["allowed"] is False
    assert result["reason"] == "disabled"
    assert result["inference_called"] is False


def test_budgeted_inference_source_has_no_camera_network_or_endpoint_calls():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                if root in {"cv2", "requests", "httpx", "ollama"}:
                    forbidden.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0].lower()
            if root in {"cv2", "requests", "httpx", "ollama"}:
                forbidden.append((node.module, node.lineno))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"VideoCapture"}:
                forbidden.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                root = _root_name(node.func.value)
                attr = node.func.attr
                if root in {"requests", "httpx"} and attr in {"get", "post", "request", "send"}:
                    forbidden.append((f"{root}.{attr}", node.lineno))
                if root == "ollama" and attr in {"generate", "chat"}:
                    forbidden.append((f"{root}.{attr}", node.lineno))
                if attr in {"read", "imshow"}:
                    forbidden.append((attr, node.lineno))

    assert forbidden == []
    for endpoint in ["/camera/start", "/camera/snap", "/camera/video", "/vlm/analyze", "/vlm/caption"]:
        assert endpoint not in source
