from __future__ import annotations

from remote_multimodal.engine import MultiModalEngine
from remote_multimodal.models import AnalyzeRequest


def test_analyze_request_accepts_semantic_budget_fields():
    req = AnalyzeRequest(
        image_b64="abc",
        requested_tasks=["objects", "hazards"],
        run_semantic_vlm=False,
        semantic_reason="scene_change",
        request_id="vlm-1",
    )
    assert req.run_semantic_vlm is False
    assert req.semantic_reason == "scene_change"
    assert req.request_id == "vlm-1"


def test_remote_engine_qwen_budget_decision_is_explicit():
    assert MultiModalEngine._should_run_qwen({"objects", "hazards"}, False) is False
    assert MultiModalEngine._should_run_qwen({"objects"}, True) is True
    # Legacy clients without explicit flag keep old hazard/semantic behavior.
    assert MultiModalEngine._should_run_qwen({"hazards"}, None) is True
    assert MultiModalEngine._should_run_qwen({"objects"}, None) is False
