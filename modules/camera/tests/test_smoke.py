from __future__ import annotations

import importlib.util
import pytest


def test_camera_service_import_and_factory_presence():
    """
    Smoke test for camera module.
    - If OpenCV (cv2) is not installed in the environment, skip to avoid false failures.
    - Otherwise, verify that create_app factory exists (without instantiating it to avoid hardware access).
    """
    if importlib.util.find_spec("cv2") is None:
        pytest.skip("cv2 not installed; skipping camera smoke test")

    # Import lazily after dependency check to prevent ImportError on environments without cv2
    from modules.camera import xCameraService as cam

    assert hasattr(cam, "create_app") and callable(getattr(cam, "create_app"))
