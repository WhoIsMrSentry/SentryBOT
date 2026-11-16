from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from remote_multimodal.config import RuntimeConfig, load_runtime_config
from remote_multimodal.engine import MultiModalEngine
from remote_multimodal.onsensor_hints import parse_onsensor_hints
from remote_multimodal.qwen_client import QwenVlmClient
from remote_multimodal.server import _QWEN_PROBE_CACHE, create_app


def _tiny_jpeg_b64(width: int = 160, height: int = 160) -> str:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


def test_lazy_backends_on_create_app_and_lifespan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = RuntimeConfig(
        face_db_path=str(tmp_path / "faces.json"),
        detector_backend="opencv",
        enable_face_recognition=False,
        enable_age_emotion=False,
        enable_qwen_vlm=False,
        enable_advanced_caption=False,
        enable_ocr=False,
    )
    app = create_app(cfg, lazy_backends=True)
    # App creation does not eagerly block/load heavy backends before lifespan starts
    assert app is not None

    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["backends"]["loaded"] is True


def test_healthz_reports_vram_backends_and_cached_qwen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _QWEN_PROBE_CACHE.clear()

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            mem_get_info=lambda: (2 * 1024**3, 8 * 1024**3),
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    probe_mock = MagicMock(return_value=SimpleNamespace(status_code=200))
    monkeypatch.setattr("remote_multimodal.server.requests.get", probe_mock)

    cfg = RuntimeConfig(
        face_db_path=str(tmp_path / "faces.json"),
        detector_backend="opencv",
        enable_face_recognition=False,
        enable_age_emotion=False,
        enable_qwen_vlm=True,
        qwen_endpoint="http://127.0.0.1:11434/api/chat",
        enable_advanced_caption=False,
        enable_ocr=False,
    )
    app = create_app(cfg, lazy_backends=True)
    with TestClient(app) as client:
        r1 = client.get("/healthz")
        r2 = client.get("/healthz")

    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["vram"]["available"] is True
    assert d1["vram"]["total_mb"] == 8192.0
    assert d1["vram"]["used_mb"] == 6144.0
    assert d1["qwen"]["reachable"] is True
    assert d1["qwen"]["cached"] is False
    assert r2.json()["qwen"]["cached"] is True
    assert probe_mock.call_count == 1


def test_auth_401_oversize_413_bad_b64_400_and_ocr_languages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    img_b64 = _tiny_jpeg_b64()
    cfg = RuntimeConfig(
        auth_token="gpu-secret-token",
        face_db_path=str(tmp_path / "faces.json"),
        detector_backend="opencv",
        enable_face_recognition=False,
        enable_age_emotion=False,
        enable_qwen_vlm=False,
        enable_advanced_caption=False,
        enable_ocr=True,
        max_image_b64_bytes=max(32, len(img_b64) + 10),
    )
    app = create_app(cfg, lazy_backends=False)
    client = TestClient(app)

    # Auth guard (missing & wrong token -> 401)
    assert client.post("/vision/analyze/cheap", json={"image_b64": img_b64}).status_code == 401
    assert (
        client.post(
            "/vision/analyze/cheap",
            headers={"X-Auth-Token": "wrong"},
            json={"image_b64": img_b64},
        ).status_code
        == 401
    )

    # Oversized payload -> 413
    too_big = "A" * (cfg.max_image_b64_bytes + 5)
    assert (
        client.post(
            "/vision/analyze/cheap",
            headers={"X-Auth-Token": "gpu-secret-token"},
            json={"image_b64": too_big},
        ).status_code
        == 413
    )

    # Corrupt base64 -> 400
    assert (
        client.post(
            "/vision/analyze/cheap",
            headers={"X-Auth-Token": "gpu-secret-token"},
            json={"image_b64": "!!!not-base64!!!"},
        ).status_code
        == 400
    )

    # /vision/ocr forwards languages parameter to engine/ocr_frame
    seen_langs: list = []

    def _fake_ocr(_frame, languages=None):
        seen_langs.append(languages)
        return {"ok": True, "text": "Merhaba", "lines": []}

    monkeypatch.setattr(MultiModalEngine, "ocr_frame", lambda self, f, languages=None: _fake_ocr(f, languages=languages))
    ocr_resp = client.post(
        "/vision/ocr",
        headers={"X-Auth-Token": "gpu-secret-token"},
        json={"image_b64": img_b64, "languages": ["tr", "en"]},
    )
    assert ocr_resp.status_code == 200
    assert seen_langs == [["tr", "en"]]


def test_env_overrides_preserved_over_profile_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MM_FACE_DB", str(tmp_path / "faces.json"))
    monkeypatch.setenv("MM_DETECTOR_BACKEND", "opencv")
    monkeypatch.setenv("MM_ENABLE_FACE_RECOGNITION", "false")
    monkeypatch.setenv("MM_ENABLE_QWEN_VLM", "false")
    monkeypatch.setenv("MM_ENABLE_OCR", "false")
    monkeypatch.setenv("MM_RUNTIME_PROFILE", "ultra_fast")
    monkeypatch.setenv("MM_YOLO_CONF", "0.77")
    monkeypatch.setenv("MM_YOLO_IMGSZ", "640")
    monkeypatch.setenv("MM_QWEN_TIMEOUT", "19.5")

    cfg = load_runtime_config()
    engine = MultiModalEngine(cfg, lazy_backends=True)
    assert engine.cfg.yolo_conf == pytest.approx(0.77)
    assert engine.cfg.yolo_imgsz == 640
    assert engine.cfg.qwen_timeout_s == pytest.approx(19.5)


def test_cheap_skips_caption_and_qwen_reuses_b64_and_dict_hazards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = RuntimeConfig(
        face_db_path=str(tmp_path / "faces.json"),
        detector_backend="opencv",
        enable_face_recognition=False,
        enable_age_emotion=False,
        enable_qwen_vlm=True,
        enable_advanced_caption=True,
        enable_ocr=False,
    )
    engine = MultiModalEngine(cfg, lazy_backends=True)
    # Prevent live HuggingFace model download during unit test
    engine.backends._loaded = True
    caption_calls = 0

    def _count_caption(_frame):
        nonlocal caption_calls
        caption_calls += 1
        return "heavy caption"

    monkeypatch.setattr(engine, "_caption", _count_caption)
    img_b64 = _tiny_jpeg_b64()
    cheap_res = engine.analyze_cheap(img_b64)
    assert cheap_res["ok"] is True
    assert caption_calls == 0

    # Dict hazard items from Qwen are parsed cleanly in semantic mode
    monkeypatch.setattr(
        engine.qwen,
        "analyze_frame",
        lambda frame, **kw: {
            "ok": True,
            "model": "qwen3.5:9b",
            "scene_summary": "A stove on fire",
            "answer": "",
            "hazards": [{"type": "fire", "severity": "high", "bbox": [1, 2, 10, 20]}],
            "latency_ms": 12.0,
        },
    )
    sem_res = engine.analyze_semantic(img_b64, semantic_reason="hazard")
    assert any("fire" in str(h).lower() for h in sem_res["hazards"])

    # QwenVlmClient reuses incoming image_b64 without calling _encode_frame when frame fits width
    qwen = QwenVlmClient(cfg)
    monkeypatch.setattr(qwen, "_encode_frame", MagicMock(side_effect=AssertionError("must not re-encode")))
    monkeypatch.setattr(
        qwen,
        "_call_model",
        lambda model, image_b64, question="", semantic_reason="": {"ok": True, "b64": image_b64},
    )
    small_frame = np.zeros((100, 200, 3), dtype=np.uint8)
    qwen_out = qwen.analyze_frame(small_frame, image_b64="REUSED_B64")
    assert qwen_out == {"ok": True, "b64": "REUSED_B64"}


def test_register_face_atomic_and_onsensor_negative_age_rejected(tmp_path: Path) -> None:
    face_db = tmp_path / "faces.json"
    cfg = RuntimeConfig(
        face_db_path=str(face_db),
        detector_backend="opencv",
        enable_face_recognition=True,
        enable_age_emotion=False,
        enable_qwen_vlm=False,
        enable_advanced_caption=False,
        enable_ocr=False,
    )
    engine = MultiModalEngine(cfg, lazy_backends=True)
    engine.backends._loaded = True
    engine.backends.face_recognition = SimpleNamespace(
        face_locations=lambda _rgb, model="hog": [(10, 50, 50, 10)],
        face_encodings=lambda _rgb, _locs=None: [np.ones(128, dtype=np.float32)],
    )
    res = engine.register_face("Alice", _tiny_jpeg_b64())
    assert res["ok"] is True
    assert face_db.exists()
    assert not (tmp_path / "faces.json.tmp").exists()
    assert json.loads(face_db.read_text(encoding="utf-8"))[0]["name"] == "Alice"

    assert (
        parse_onsensor_hints(
            {"schema": "onsensor_hints@1", "age_s": -0.25, "detections": []},
        )
        is None
    )
