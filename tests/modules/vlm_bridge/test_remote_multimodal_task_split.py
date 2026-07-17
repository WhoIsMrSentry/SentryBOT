from __future__ import annotations

from modules.vlm_bridge.services.processor import VisionProcessor


def test_remote_multimodal_endpoint_split_defaults_from_base_endpoint():
    p = VisionProcessor({
        "vision": {"processing_mode": "remote"},
        "vision_llm": {"enabled": False},
        "remote_multimodal": {
            "enabled": True,
            "endpoint": "http://pc:8091/vision/analyze",
        },
    })
    assert p._remote_multimodal_endpoint_for(False).endswith("/vision/analyze/cheap")
    assert p._remote_multimodal_endpoint_for(True).endswith("/vision/analyze/semantic")


def test_remote_multimodal_endpoint_split_honors_explicit_config():
    p = VisionProcessor({
        "vision": {"processing_mode": "remote"},
        "vision_llm": {"enabled": False},
        "remote_multimodal": {
            "enabled": True,
            "endpoint": "http://pc:8091/vision/analyze",
            "cheap_endpoint": "http://pc:8091/custom/cheap",
            "semantic_endpoint": "http://pc:8091/custom/semantic",
        },
    })
    assert p._remote_multimodal_endpoint_for(False) == "http://pc:8091/custom/cheap"
    assert p._remote_multimodal_endpoint_for(True) == "http://pc:8091/custom/semantic"
