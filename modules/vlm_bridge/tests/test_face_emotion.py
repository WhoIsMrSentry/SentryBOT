"""Tests for lightweight FER service."""
from __future__ import annotations

import numpy as np

from modules.vlm_bridge.services.face_emotion import FaceEmotionEstimator


def test_heuristic_returns_emotion_dict():
    est = FaceEmotionEstimator({"backend": "heuristic", "min_confidence": 0.2})
    dark = np.full((48, 48), 40, dtype=np.uint8)
    out = est.estimate(dark)
    assert "emotion" in out
    assert "confidence" in out
    assert out["backend"] == "heuristic"


def test_none_backend_is_neutral():
    est = FaceEmotionEstimator({"backend": "none"})
    out = est.estimate(None)
    assert out["emotion"] == "neutral"
