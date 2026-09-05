"""Device lock, reference tracking, and handle abstractions for Camera Device Manager."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

class CameraMode(str, Enum):
    """Camera processing modes."""
    LOCAL = "local"           # Full local processing (OpenCV face detect)
    REMOTE = "remote"         # Stream to remote PC for VLM
    ONSENSOR = "onsensor"     # IMX500 on-sensor inference
    HYBRID = "hybrid"         # Local capture + remote processing

@dataclass
class CameraConfig:
    """Camera device configuration."""
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    format: str = "RGB888"
    mode: CameraMode = CameraMode.LOCAL
    imx500_enabled: bool = False
    imx500_model_path: str = ""
    imx500_labels_path: str = ""
    imx500_confidence: float = 0.5
    hybrid_local_capture: bool = True

class DeviceState(str, Enum):
    """Camera device states."""
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    STREAMING = "streaming"
    ERROR = "error"
    RECOVERING = "recovering"

@dataclass
class DeviceRef:
    """Reference to an open device."""
    owner: str
    mode: CameraMode
    opened_at: float
    ref_count: int = 1

class DeviceHandle:
    """Handle for a camera device reference."""

    def __init__(self, manager: Any, owner: str):
        self._manager = manager
        self._owner = owner
        self._released = False

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def manager(self) -> Any:
        return self._manager

    def release(self) -> bool:
        """Release this reference."""
        if self._released:
            return False
        self._released = True
        return self._manager.release(self._owner)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __del__(self):
        if not self._released:
            try:
                self.release()
            except Exception:
                pass
