"""Remote FER backend tests."""
from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock, patch

from modules.vlm_bridge.services.face_emotion import FaceEmotionEstimator


def test_remote_fer_uses_http_response():
    est = FaceEmotionEstimator(
        {
            "backend": "remote",
            "remote_url": "http://127.0.0.1:9999/fer",
            "remote_fallback": "heuristic",
        }
    )
    face = np.full((48, 48, 3), 120, dtype=np.uint8)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"emotion": "happy", "confidence": 0.82}

    with patch.object(est, "_encode_face_b64", return_value="ZmFrZQ=="), patch(
        "requests.post", return_value=mock_resp
    ):
        out = est.estimate(face)
    assert out["emotion"] == "joy"
    assert out["backend"] == "remote"
