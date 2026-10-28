"""onsensor_hints@1 contract tests (robot side): payload wiring + task split."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import modules.vlm_bridge.services.processor_vlm as pv_mod
from modules.vlm_bridge.services.onsensor_hints import HINTS_SCHEMA, build_onsensor_hints
from modules.vlm_bridge.services.processor_vlm_signals import ProcessorVlmSignalsMixin


class _Det:
    def __init__(self, label: str, score: float, bbox, track_id=None):
        self.label = label
        self.score = score
        self.bbox_xyxy_norm = bbox
        self.track_id = track_id
        self.class_id = 0


class _Snap:
    def __init__(self, detections, ts=None, backend="imx500"):
        self.detections = detections
        self.ts = time.time() if ts is None else ts
        self.backend = backend
        self.width = 1920
        self.height = 1080
        self.frame_id = 1
        self.target_track_id = None
        self.target_label = ""


class _T(ProcessorVlmSignalsMixin):
    pass


def _stub_t(snap, split=True, hints_enabled=True) -> _T:
    t = _T()
    t.mode_categories = {"onsensor": {"tiny_detect": True}, "remote": {"objects": True, "people": True,
                                                                      "faces": True, "hazards": True,
                                                                      "semantic_scene": True}}
    t._onsensor_lock = None
    t._latest_onsensor = snap
    t._latest_onsensor_snapshot = lambda: snap
    t._onsensor_active = lambda: True
    t.remote_mm_task_split_enabled = split
    t.remote_mm_onsensor_hints_enabled = hints_enabled
    t.remote_mm_task_split_skip = ["people", "faces"]
    return t


def test_build_onsensor_hints_schema():
    snap = _Snap([_Det("person", 0.91, (0.1, 0.2, 0.4, 0.8), 3),
                  _Det("chair", 0.55, (0.5, 0.5, 0.9, 1.0))])
    hints = build_onsensor_hints(snap, (1080, 1920))
    assert hints["schema"] == HINTS_SCHEMA
    assert hints["backend"] == "imx500"
    assert hints["frame"] == {"w": 1920, "h": 1080}
    assert len(hints["detections"]) == 2
    person = hints["detections"][0]
    assert person["label"] == "person" and person["source"] == "onsensor"
    assert person["bbox_xyxy"][0] == 192 and 864 <= person["bbox_xyxy"][3] <= 1080
    assert person["track_id"] == 3


def test_build_onsensor_hints_stale_snapshot_is_none():
    old = _Snap([_Det("person", 0.9, (0.1, 0.1, 0.3, 0.3))], ts=time.time() - 10.0)
    assert build_onsensor_hints(old) is None


def test_task_split_skips_people_faces_when_person_fresh():
    snap = _Snap([_Det("person", 0.9, (0.1, 0.1, 0.3, 0.4))])
    t = _stub_t(snap)
    tasks = t._remote_requested_tasks(run_semantic_vlm=True)
    assert "people" not in tasks and "faces" not in tasks
    assert "objects" in tasks and "semantic_scene" in tasks and "hazards" in tasks


def test_task_split_keeps_all_tasks_without_person():
    snap = _Snap([_Det("chair", 0.6, (0.5, 0.5, 0.9, 0.9))])
    t = _stub_t(snap)
    tasks = t._remote_requested_tasks(run_semantic_vlm=False)
    assert "people" in tasks and "faces" in tasks


def test_task_split_config_off_restores_legacy():
    snap = _Snap([_Det("person", 0.9, (0.1, 0.1, 0.3, 0.4))])
    t = _stub_t(snap, split=False)
    tasks = t._remote_requested_tasks(run_semantic_vlm=False)
    assert "people" in tasks and "faces" in tasks


def _mm_stub(monkeypatch, capture: Dict[str, Any], ok=True):
    class _Resp:
        status_code = 200 if ok else 503

        def json(self):
            return {"ok": ok}

    def fake_post(endpoint, json=None, headers=None, timeout=0):
        capture["endpoint"] = endpoint
        capture["payload"] = dict(json or {})
        return _Resp()

    monkeypatch.setattr(pv_mod.requests, "post", fake_post)


class _MM(pv_mod.ProcessorVlmMixin):
    pass


def _minimal_processor(monkeypatch_capture: Dict[str, Any], monkeypatch) -> Any:
    from types import SimpleNamespace

    mm = _MM.__new__(_MM)
    mm.remote_mm_enabled = True
    mm.remote_mm_endpoint = "http://pc:8091/vision/analyze"
    mm.remote_mm_cheap_endpoint = "http://pc:8091/vision/analyze/cheap"
    mm.remote_mm_semantic_endpoint = "http://pc:8091/vision/analyze/semantic"
    mm.remote_mm_timeout_s = 2.0
    mm.remote_mm_auth_token = "tok"
    mm.remote_mm_fail_count = 0
    mm.remote_mm_max_fail_count = 3
    mm.remote_mm_last_ok_ts = 0.0
    mm.remote_mm_task_split_enabled = True
    mm.remote_mm_onsensor_hints_enabled = True
    mm.remote_mm_task_split_skip = ["people", "faces"]
    mm.mode_categories = {"onsensor": {"tiny_detect": True}, "remote": {"objects": True, "people": True,
                                                                        "faces": True, "hazards": True}}
    snap = _Snap([_Det("person", 0.88, (0.2, 0.2, 0.8, 0.6), 5)])
    mm._latest_onsensor_snapshot = lambda: snap
    mm._onsensor_active = lambda: True

    frame = SimpleNamespace(shape=(96, 128, 3))
    buf_stub = SimpleNamespace(tobytes=lambda: b"\x00\x01")
    monkeypatch.setattr(pv_mod.cv2, "imencode", lambda *a, **k: (True, buf_stub))
    _mm_stub(monkeypatch, monkeypatch_capture)
    return mm, frame


def test_remote_call_payload_carries_semantic_question_and_hints(monkeypatch):
    cap: Dict[str, Any] = {}
    mm, frame = _minimal_processor(cap, monkeypatch)
    hints = build_onsensor_hints(mm._latest_onsensor_snapshot(), frame.shape)
    out = mm._call_remote_multimodal(
        frame, run_semantic_vlm=True, question="goruntude kac kisi var?",
        semantic_reason="user_question", onsensor_hints=hints, request_id="r1",
    )
    assert out is not None
    payload = cap["payload"]
    assert cap["endpoint"].endswith("/vision/analyze/semantic")
    assert payload["question"] == "goruntude kac kisi var?"
    assert payload["run_semantic_vlm"] is True
    assert payload["onsensor_hints"]["schema"] == HINTS_SCHEMA
    assert "people" not in payload["requested_tasks"] and "faces" not in payload["requested_tasks"]


def test_remote_health_failover(monkeypatch):
    cap: Dict[str, Any] = {}
    mm, frame = _minimal_processor(cap, monkeypatch)

    class _Fail:
        status_code = 503

        def json(self):
            return {}

    monkeypatch.setattr(pv_mod.requests, "post", lambda *a, **k: _Fail())
    for _ in range(3):
        assert mm._call_remote_multimodal(frame) is None
    assert mm.remote_mm_fail_count == 3
    health = mm.remote_mm_health()
    assert health["healthy"] is False
    monkeypatch.setattr(pv_mod.requests, "post", lambda *a, **k: _Fail())
    assert mm._call_remote_multimodal(frame) is None  # failover blocks further calls
    cap["_fail_blocked"] = True
