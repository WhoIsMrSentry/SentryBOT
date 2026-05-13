"""Camera service exports with lazy submodule loading.

We avoid eagerly importing :mod:`.capture` (which depends on ``cv2``) at
package import time so test environments without a working OpenCV install can
still import :mod:`modules.camera.services.imx500_runner` and
:mod:`modules.camera.services.onsensor_bus` without crashing.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CameraCapture",
    "FramePublisher",
    "OnSensorDetection",
    "OnSensorEventBus",
    "OnSensorSnapshot",
    "get_default_bus",
    "set_default_bus",
    "Imx500Config",
    "Imx500Runner",
    "IMX500_AVAILABLE",
    "IMX500_IMPORT_ERROR",
]


_ATTR_TO_MODULE = {
    "CameraCapture": ".capture",
    "FramePublisher": ".capture",
    "OnSensorDetection": ".onsensor_bus",
    "OnSensorEventBus": ".onsensor_bus",
    "OnSensorSnapshot": ".onsensor_bus",
    "get_default_bus": ".onsensor_bus",
    "set_default_bus": ".onsensor_bus",
    "Imx500Config": ".imx500_runner",
    "Imx500Runner": ".imx500_runner",
    "IMX500_AVAILABLE": ".imx500_runner",
    "IMX500_IMPORT_ERROR": ".imx500_runner",
}


def __getattr__(name: str) -> Any:
    target = _ATTR_TO_MODULE.get(name)
    if target is None:
        raise AttributeError(name)
    module = importlib.import_module(target, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
