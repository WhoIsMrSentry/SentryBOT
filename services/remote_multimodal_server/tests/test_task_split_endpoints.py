from __future__ import annotations

import base64
from types import SimpleNamespace

import cv2
import numpy as np

from remote_multimodal.config import RuntimeConfig
from remote_multimodal.engine import MultiModalEngine
from remote_multimodal.models import AnalyzeRequest


def _jpeg_b64() -> str:
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


class _FakeQwen:
    def __init__(self):
        self.calls = 0

    def analyze_frame(self, frame):
        self.calls += 1
        return {
            "ok": True,
            "model": "fake-qwen",
            "summary": "semantic scene",
            "persona_interpretation": "semantic scene",
            "hazards": [],
            "suggested_focus": "scene",
        }


def _engine() -> MultiModalEngine:
    e = MultiModalEngine.__new__(MultiModalEngine)
    e.cfg = RuntimeConfig(enable_qwen_vlm=True)
    e.backends = SimpleNamespace(
        yolo=None,
        face_recognition=None,
        deepface=None,
        caption_pipe=None,
        ocr_backend_name=None,
    )
    e.qwen = _FakeQwen()
    e.detect_objects = lambda frame: []
    e.detect_faces = lambda frame: []
    e.motion_scene_change = lambda frame: (0.0, 0.0)
    e._caption = lambda frame: None
    e.ocr_frame = lambda frame: {"ok": False}
    return e


def test_analyze_request_accepts_task_mode():
    req = AnalyzeRequest(image_b64="abc", mode="cheap")
    assert req.mode == "cheap"


def test_cheap_endpoint_never_calls_qwen():
    e = _engine()
    out = e.analyze_cheap(_jpeg_b64(), request_id="cheap-1")
    assert out["backend_info"]["task_mode"] == "cheap"
    assert out["backend_info"]["semantic_vlm_requested"] is False
    assert e.qwen.calls == 0


def test_semantic_endpoint_calls_qwen():
    e = _engine()
    out = e.analyze_semantic(_jpeg_b64(), semantic_reason="user_question", request_id="sem-1")
    assert out["backend_info"]["task_mode"] == "semantic"
    assert out["backend_info"]["semantic_vlm_requested"] is True
    assert out["backend_info"]["qwen_vlm"] is True
    assert e.qwen.calls == 1
