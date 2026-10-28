"""Server-side onsensor_hints@1 merge + task split tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("cv2")
import cv2
import numpy as np

from remote_multimodal.config import RuntimeConfig
from remote_multimodal.engine import MultiModalEngine
from remote_multimodal.onsensor_hints import HINTS_SCHEMA, parse_onsensor_hints

import base64


def _jpeg_b64() -> str:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _engine() -> MultiModalEngine:
    e = MultiModalEngine.__new__(MultiModalEngine)
    e.cfg = RuntimeConfig(enable_qwen_vlm=False)
    e.backends = SimpleNamespace(
        yolo=None,
        face_recognition=None,
        deepface=None,
        caption_pipe=None,
        ocr_backend_name=None,
    )
    e.qwen = SimpleNamespace(
        analyze_frame=lambda frame, question="", semantic_reason="": {"ok": False}
    )
    e.face_cascade_calls = 0

    def _spy_faces(frame):
        e.face_cascade_calls += 1
        return []

    e.detect_faces = _spy_faces
    e.detect_objects = lambda frame: [{"label": "chair", "confidence": 0.7, "bbox": [5, 5, 30, 40]}]
    e.motion_scene_change = lambda frame: (0.0, 0.0)
    e._caption = lambda frame: None
    e.ocr_frame = lambda frame: {"ok": False}
    e.recognize_person = lambda frame, box: ("Emir", 0.9)
    e.estimate_age_emotion = lambda crop: (None, "neutral")
    return e


def _hints() -> dict:
    return {
        "schema": HINTS_SCHEMA,
        "backend": "imx500",
        "age_s": 0.4,
        "detections": [
            {"label": "person", "confidence": 0.92, "bbox_xyxy_norm": [0.1, 0.1, 0.5, 0.9], "track_id": 2,
             "source": "onsensor"},
            {"label": "knife", "confidence": 0.81, "bbox_xyxy_norm": [0.6, 0.6, 0.9, 0.9], "source": "onsensor"},
        ],
    }


def test_parse_validates_and_normalizes():
    parsed = parse_onsensor_hints(_hints(), 48, 64)
    assert parsed is not None
    assert len(parsed["people"]) == 1
    person = parsed["people"][0]
    assert person["bbox_xyxy"][0] == 6  # 0.1 * 64
    assert parsed["detections"][0]["source"] == "onsensor"


def test_parse_rejects_old_schema_and_stale():
    bad = {"schema": "onsensor_hints@0"}
    assert parse_onsensor_hints(bad) is None
    stale = _hints()
    stale["age_s"] = 10.0
    assert parse_onsensor_hints(stale) is None


def test_person_hints_skip_own_face_detection_and_merge():
    e = _engine()
    out = e.analyze(
        _jpeg_b64(),
        requested_tasks=["objects", "people", "faces", "hazards"],
        run_semantic_vlm=False,
        task_mode="cheap",
        onsensor_hints=_hints(),
    )
    assert e.face_cascade_calls == 0  # IMX500 owns person identity work
    assert len(out["people"]) == 1
    assert out["people"][0]["source"] == "onsensor"
    assert out["people"][0]["bbox"] == [6, 4, 32, 43]
    labels = [o["label"] for o in out["objects"]]
    assert "chair" in labels and "knife" in labels  # own CV + hints merged
    sources = {o["label"]: o["source"] for o in out["objects"]}
    assert sources["chair"] == "remote_cv" and sources["knife"] == "onsensor"
    assert out["sources"]["onsensor_people"] == 1
    assert out["sources"]["hints_schema"] == HINTS_SCHEMA


def test_without_person_hints_own_detection_still_runs():
    e = _engine()
    out = e.analyze(_jpeg_b64(), requested_tasks=["people", "faces"], run_semantic_vlm=False, task_mode="cheap")
    assert e.face_cascade_calls == 1
    assert out["objects"] == [] or all(o.get("label") != "chair" for o in out["objects"])
    assert "onsensor" not in out["sources"]["hints_schema"]


def test_hints_objects_and_hazards_alone_without_cv_objects():
    e = _engine()
    e.detect_objects = lambda frame: []
    out = e.analyze(_jpeg_b64(), onsensor_hints=_hints(), run_semantic_vlm=False, task_mode="cheap")
    hazards = [h["type"] for h in out["hazards"]]
    assert "knife" in hazards and out["hazards"][0]["source"] == "onsensor"
    assert out["importance_score"] >= 0.6
