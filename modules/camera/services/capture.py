from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import cv2  # type: ignore
except Exception as exc:
    cv2 = None  # type: ignore
    CV2_IMPORT_ERROR: Optional[str] = repr(exc)
else:
    CV2_IMPORT_ERROR = None

PICAM_AVAILABLE = False
PICAM_IMPORT_ERROR: Optional[str] = None
Picamera2 = None  # type: ignore

try:
    from picamera2 import Picamera2 as _PicamClass  # type: ignore

    Picamera2 = _PicamClass
    PICAM_AVAILABLE = True
except Exception as exc:
    PICAM_IMPORT_ERROR = repr(exc)
    for path in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
    try:
        from picamera2 import Picamera2 as _PicamClass  # type: ignore

        Picamera2 = _PicamClass
        PICAM_AVAILABLE = True
        PICAM_IMPORT_ERROR = None
    except Exception as second_exc:
        Picamera2 = None
        PICAM_IMPORT_ERROR = repr(second_exc)

from modules.common.runtime_target import assert_raspberry_pi
from .capture_bridge import BRIDGE_WORKER_CODE, find_system_picam_python
from .capture_loops import CaptureLoopsMixin

_SYSTEM_PICAM_PYTHON = find_system_picam_python()
if Picamera2 is None and _SYSTEM_PICAM_PYTHON is not None:
    PICAM_AVAILABLE = True
    PICAM_IMPORT_ERROR = None

logger = logging.getLogger("camera.capture")
MetadataListener = Callable[[Dict[str, Any]], None]


@dataclass
class CaptureConfig:
    size: Tuple[int, int] = (1280, 720)
    pixel_format: str = "RGB888"
    frame_rate: int = 30
    target_fps: int = 30
    backend: str = "picamera2"
    jpeg_quality: int = 80
    flip: str = "none"
    camera_num: int = 0


CAMERA_CAPTURE_LAZY_OPEN_CONTRACT = True
CAMERA_CAPTURE_IMPORT_STARTS_DEVICE = False
CAMERA_START_STOP_REQUIRES_EXPLICIT_ROUTE_CALL = True
CAMERA_CAPTURE_STATUS_TRUTH_CONTRACT = True
CAMERA_CAPTURE_STATUS_ROLE = "capture_state_truth_provider"
CAMERA_CAPTURE_STATUS_DOES_NOT_OPEN_DEVICE = True


class FramePublisher:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._frame_bytes: Optional[bytes] = None
        self._frame_ts = 0.0
        self._frame_count = 0

    def set_jpeg(self, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._frame_bytes = jpeg_bytes
            self._frame_ts = 0.0
            self._frame_count += 1

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._frame_bytes

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "has_frame": self._frame_bytes is not None,
                "frame_count": self._frame_count,
                "last_frame_age_s": max(0.0, 0.0 - self._frame_ts) if self._frame_ts else None,
            }


class CameraCapture(CaptureLoopsMixin):
    def __init__(self, cfg: CaptureConfig, publisher: FramePublisher) -> None:
        self.cfg = cfg
        self.pub = publisher
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._picam: Optional[Any] = None
        self._proc: Optional[subprocess.Popen] = None
        self._cv2_cap: Optional[Any] = None
        self._listeners_lock = threading.RLock()
        self._metadata_listeners: List[MetadataListener] = []
        self._last_error = ""

    @property
    def picam(self) -> Optional[Any]:
        return self._picam

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    @property
    def gave_up(self) -> bool:
        return bool(self._last_error and not self.running)

    def subscribe_metadata(self, listener: MetadataListener) -> Callable[[], None]:
        with self._listeners_lock:
            self._metadata_listeners.append(listener)

        def unsubscribe() -> None:
            with self._listeners_lock:
                if listener in self._metadata_listeners:
                    self._metadata_listeners.remove(listener)

        return unsubscribe

    def start(self) -> bool:
        if self.running:
            return True
        assert_raspberry_pi()

        if Picamera2 is not None:
            if cv2 is None:
                raise RuntimeError(f"OpenCV JPEG encoder unavailable: {CV2_IMPORT_ERROR}")
            try:
                camera = Picamera2(int(self.cfg.camera_num))
                controls = {"FrameRate": float(max(1, self.cfg.frame_rate))}
                configuration = camera.create_video_configuration(
                    main={"size": tuple(self.cfg.size), "format": str(self.cfg.pixel_format)},
                    controls=controls,
                    buffer_count=6,
                    queue=True,
                )
                camera.configure(configuration)
                camera.start()
                self._picam = camera
                self._stop.clear()
                self._last_error = ""
                self._thread = threading.Thread(target=self._capture_loop, name="picamera2-capture", daemon=True)
                self._thread.start()
                return True
            except Exception as exc:
                logger.warning("In-process Picamera2 start failed: %s; trying bridge...", exc)

        sys_py = find_system_picam_python() or _SYSTEM_PICAM_PYTHON
        if sys_py is not None:
            try:
                self._stop.clear()
                self._last_error = ""
                args = [
                    sys_py,
                    "-c",
                    BRIDGE_WORKER_CODE,
                    str(self.cfg.camera_num),
                    str(self.cfg.size[0]),
                    str(self.cfg.size[1]),
                    str(self.cfg.frame_rate),
                    str(self.cfg.jpeg_quality),
                    str(self.cfg.flip),
                    str(self.cfg.pixel_format),
                ]
                self._proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
                self._thread = threading.Thread(target=self._bridge_capture_loop, name="picamera2-bridge-capture", daemon=True)
                self._thread.start()
                logger.info("Picamera2 system bridge capture started via %s", sys_py)
                return True
            except Exception as exc:
                logger.warning("Picamera2 system bridge start failed: %s; trying cv2...", exc)

        if cv2 is not None:
            try:
                cap = cv2.VideoCapture(int(self.cfg.camera_num))
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.size[0])
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.size[1])
                    cap.set(cv2.CAP_PROP_FPS, self.cfg.frame_rate)
                    self._cv2_cap = cap
                    self._stop.clear()
                    self._last_error = ""
                    self._thread = threading.Thread(target=self._cv2_capture_loop, name="cv2-capture", daemon=True)
                    self._thread.start()
                    logger.info("OpenCV VideoCapture started for camera %s", self.cfg.camera_num)
                    return True
            except Exception as exc:
                logger.warning("OpenCV VideoCapture start failed: %s", exc)

        raise RuntimeError(f"Picamera2 unavailable: {PICAM_IMPORT_ERROR or 'No suitable camera backend'}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        if self._proc is not None:
            try:
                if self._proc.stdout is not None:
                    try:
                        self._proc.stdout.close()
                    except Exception:
                        pass
                if self._proc.stderr is not None:
                    try:
                        self._proc.stderr.close()
                    except Exception:
                        pass
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        camera = self._picam
        self._picam = None
        if camera is not None:
            try:
                camera.stop()
            except Exception:
                pass
            try:
                camera.close()
            except Exception:
                pass

        if self._cv2_cap is not None:
            try:
                self._cv2_cap.release()
            except Exception:
                pass
            self._cv2_cap = None

    def status(self) -> Dict[str, Any]:
        backend = "picamera2"
        if self._proc is not None:
            backend = "picamera2_bridge"
        elif self._cv2_cap is not None:
            backend = "opencv_v4l2"

        return {
            "backend": backend,
            "camera_num": int(self.cfg.camera_num),
            "size": {"width": int(self.cfg.size[0]), "height": int(self.cfg.size[1])},
            "pixel_format": str(self.cfg.pixel_format),
            "frame_rate": int(self.cfg.frame_rate),
            "jpeg_quality": int(self.cfg.jpeg_quality),
            "running": self.running,
            "gave_up": self.gave_up,
            "picamera2_available": bool(PICAM_AVAILABLE),
            "picamera2_import_error": PICAM_IMPORT_ERROR,
            "opencv_available": cv2 is not None,
            "opencv_import_error": CV2_IMPORT_ERROR,
            "last_error": self._last_error,
            **self.pub.status(),
        }

    async def mjpeg_generator(self, fps: int):
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        interval = 1.0 / max(1, int(fps))
        while True:
            frame = await asyncio.to_thread(self.pub.get_jpeg)
            if frame:
                yield boundary + frame + b"\r\n"
            await asyncio.sleep(interval)

    async def snapshot(self) -> Optional[bytes]:
        return await asyncio.to_thread(self.pub.get_jpeg)


__all__ = [
    "CameraCapture",
    "CaptureConfig",
    "FramePublisher",
    "PICAM_AVAILABLE",
    "PICAM_IMPORT_ERROR",
]
