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


def test_owner_seen_triggers_sampling_even_without_scene_churn():
    proc = _bare_processor()
    calls = {"n": 0}
    proc.refresh_visual_context = lambda question="": (calls.__setitem__("n", calls["n"] + 1) or {"summary": "owner"})  # type: ignore

    # An owner-level recognition should warrant a VLM look despite zero churn
    # (same signature on the second call -> scene_change_score == 0).
    owner_det = [{"label": "person", "name": "Emir", "recognition_level": 6}]
    proc._maybe_sample_vlm(owner_det)
    proc._maybe_sample_vlm(owner_det)

    for _ in range(50):
        if calls["n"] > 0 and not proc._vlm_refresh_inflight:
            break
        time.sleep(0.02)
    assert calls["n"] >= 1


def test_person_signals_flags_owner_and_new_person():
    proc = _bare_processor()
    owner, new = proc._person_signals([{"name": "Emir", "relationship": "owner"}])
    assert owner is True and new is True
    # second sighting of same name -> no longer "new"
    _, new_again = proc._person_signals([{"name": "Emir", "relationship": "owner"}])
    assert new_again is False


def test_hazard_signal_respects_distance_threshold():
    proc = _bare_processor()
    proc.config = {"vision": {"alerts": {"classes": ["knife"], "distance_threshold_m": 1.0}}}
    proc.mode_flags = {"hazards": True}
    assert proc._hazard_signal([{"label": "knife", "distance_m": 0.5}]) is True
    assert proc._hazard_signal([{"label": "knife", "distance_m": 2.0}]) is False
    assert proc._hazard_signal([{"label": "cup", "distance_m": 0.1}]) is False


def test_remote_ingest_drives_living_vision_sampling():
    proc = _bare_processor()
    proc.processing_mode = "remote"
    proc.mode_flags = {}
    proc.blind_mode_enabled = False
    proc.config = {}
    sampled = {"calls": []}
    proc._maybe_sample_vlm = lambda results: sampled["calls"].append(results)  # type: ignore
    proc._evaluate_alerts = lambda r: None  # type: ignore
    proc._handle_person_interactions = lambda r: None  # type: ignore

    class _Dispatcher:
        def emit_scene(self, *a, **k):
            pass

    proc.action_dispatcher = _Dispatcher()
    proc.semantic = object()

    proc.ingest_remote_results([{"label": "person", "name": "Z", "confidence": 0.8}])
    assert len(sampled["calls"]) == 1
    assert sampled["calls"][0][0]["label"] == "person"
