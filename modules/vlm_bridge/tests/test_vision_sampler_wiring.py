"""Verifies the VisionSampler is wired into the processor's living-vision loop."""

from __future__ import annotations

import time

from modules.vlm_bridge.services.processor import VisionProcessor
from modules.vlm_bridge.services.vision_sampler import VisionSampler


class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event_type, data=None):
        self.events.append((event_type, data))


def _bare_processor():
    proc = VisionProcessor.__new__(VisionProcessor)
    proc.vision_sampler = VisionSampler({"min_interval_s": 0.0, "scene_change_threshold": 0.3})
    proc.event_bus = _FakeBus()
    proc._follow_active = False
    proc._vlm_refresh_inflight = False
    proc._last_scene_signature = None
    return proc


def test_scene_change_score_detects_churn():
    proc = _bare_processor()
    # first observation establishes a baseline -> no change
    assert proc._scene_change_score([{"label": "person", "name": "A"}]) == 0.0
    # same scene -> no churn
    assert proc._scene_change_score([{"label": "person", "name": "A"}]) == 0.0
    # a new object appears -> non-zero churn
    score = proc._scene_change_score([{"label": "person", "name": "A"}, {"label": "cup", "name": ""}])
    assert score > 0.0


def test_sampler_triggers_background_refresh_and_publishes():
    proc = _bare_processor()
    calls = {"n": 0}

    def _fake_refresh(question: str = ""):
        calls["n"] += 1
        return {"summary": "a room"}

    proc.refresh_visual_context = _fake_refresh  # type: ignore[assignment]

    # establish baseline then introduce a strong scene change
    proc._maybe_sample_vlm([])
    proc._maybe_sample_vlm([{"label": "person", "name": "X"}, {"label": "dog", "name": ""}])

    # background refresh runs on a daemon thread
    for _ in range(50):
        if calls["n"] > 0 and not proc._vlm_refresh_inflight:
            break
        time.sleep(0.02)

    assert calls["n"] >= 1
    published = {evt for evt, _ in proc.event_bus.events}
    assert "scene_changed" in published
    assert "vlm_result_ready" in published


def test_follow_mode_suppresses_sampling():
    proc = _bare_processor()
    proc._follow_active = True
    proc.refresh_visual_context = lambda question="": {"summary": "x"}  # type: ignore[assignment]
    proc._maybe_sample_vlm([])
    proc._maybe_sample_vlm([{"label": "person", "name": "Y"}])
    time.sleep(0.1)
    assert proc.event_bus.events == []
