from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.common.vision_availability import (
    camera_live_available,
    remote_vision_cache_available,
    vision_input_available,
)


def test_vision_input_available_from_remote_cache():
    base = "http://127.0.0.1:8080"

    with patch("modules.common.vision_availability.camera_live_available", return_value=False):
        with patch("modules.common.vision_availability.remote_vision_cache_available", return_value=True):
            assert vision_input_available(base) is True


def test_vision_input_unavailable_when_both_missing():
    base = "http://127.0.0.1:8080"

    with patch("modules.common.vision_availability.camera_live_available", return_value=False):
        with patch("modules.common.vision_availability.remote_vision_cache_available", return_value=False):
            assert vision_input_available(base) is False


def test_remote_cache_from_results_latest():
    base = "http://127.0.0.1:8080"
    mock_resp_ctx = MagicMock(status_code=200, json=lambda: {"available": False})
    mock_resp_results = MagicMock(status_code=200, json=lambda: {"results": [{"label": "person"}]})

    with patch("requests.get", side_effect=[mock_resp_ctx, mock_resp_results]):
        assert remote_vision_cache_available(base) is True


def test_camera_live_requires_ok_not_gave_up():
    mock_resp = MagicMock(status_code=200, json=lambda: {"ok": True, "gave_up": True})

    with patch("requests.get", return_value=mock_resp):
        assert camera_live_available("http://127.0.0.1:8080") is False
