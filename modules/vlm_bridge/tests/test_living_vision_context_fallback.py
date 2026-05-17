import threading

from modules.vlm_bridge.services.processor import VisionProcessor
from modules.vlm_bridge.services.visual_context import VisualContextCache


def test_timeout_returns_cached_visual_context_fallback():
    proc = VisionProcessor.__new__(VisionProcessor)
    proc.visual_context_cache = VisualContextCache()
    proc.latest_results = [{"label": "person", "name": "Unknown", "confidence": 0.4, "bbox": [1, 1, 10, 10], "tracked": False}]
    proc._frame_lock = threading.Lock()
    proc._latest_raw_frame = None
    proc.vlm_client = None
    proc._context_max_age_s = 45.0
    proc.remote_mm_enabled = False

    # bind methods from class
    ctx = VisionProcessor.refresh_visual_context(proc, question="ne görüyorsun?")
    assert ctx is not None
    assert "summary" in ctx
    assert "importance_score" in ctx


def test_agent_core_get_visual_context_returns_latest_context():
    proc = VisionProcessor.__new__(VisionProcessor)
    proc.visual_context_cache = VisualContextCache()
    proc.latest_results = []
    proc._frame_lock = threading.Lock()
    proc._latest_raw_frame = None
    proc.vlm_client = None
    proc._context_max_age_s = 45.0

    VisionProcessor.update_visual_context(
        proc,
        {
            "timestamp": "now",
            "summary": "oda",
            "objects": [],
            "people": [],
            "hazards": [],
            "interesting_events": [],
            "recommended_focus": {"type": "none"},
            "importance_score": 0.3,
            "raw_vlm_observation": "oda",
            "persona_interpretation": "oda sakin",
        },
    )
    latest = VisionProcessor.get_latest_visual_context(proc)
    assert latest is not None
    assert latest.get("summary") == "oda"

