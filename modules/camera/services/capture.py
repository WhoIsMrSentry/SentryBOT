from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
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

try:
    from picamera2 import Picamera2  # type: ignore

    PICAM_AVAILABLE = True
except Exception as exc:
    PICAM_IMPORT_ERROR = repr(exc)
    for path in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
    try:
        from picamera2 import Picamera2  # type: ignore

        PICAM_AVAILABLE = True
        PICAM_IMPORT_ERROR = None
    except Exception as second_exc:
        Picamera2 = None  # type: ignore
        PICAM_IMPORT_ERROR = repr(second_exc)

from modules.common.runtime_target import assert_raspberry_pi

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
            self._frame_ts = time.time()
            self._frame_count += 1

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._frame_bytes

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "has_frame": self._frame_bytes is not None,
                "frame_count": self._frame_count,
                "last_frame_age_s": max(0.0, time.time() - self._frame_ts) if self._frame_ts else None,
            }


class CameraCapture:
    def __init__(self, cfg: CaptureConfig, publisher: FramePublisher) -> None:
        self.cfg = cfg
        self.pub = publisher
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._picam: Optional[Any] = None
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
        if not PICAM_AVAILABLE or Picamera2 is None:
            raise RuntimeError(f"Picamera2 unavailable: {PICAM_IMPORT_ERROR}")
        if cv2 is None:
            raise RuntimeError(f"OpenCV JPEG encoder unavailable: {CV2_IMPORT_ERROR}")

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

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
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

    def status(self) -> Dict[str, Any]:
        return {
            "backend": "picamera2",
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

    def _capture_loop(self) -> None:
        assert self._picam is not None
        while not self._stop.is_set():
            request = None
            try:
                request = self._picam.capture_request()
                metadata = dict(request.get_metadata() or {})
                frame = request.make_array("main")
                self._notify_metadata(metadata)
                frame = self._prepare_frame(frame)
                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, self.cfg.jpeg_quality)))],
                )
                if ok:
                    self.pub.set_jpeg(encoded.tobytes())
                    self._last_error = ""
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("Picamera2 capture failed: %s", exc)
                time.sleep(0.1)
            finally:
                if request is not None:
                    try:
                        request.release()
                    except Exception:
                        pass

    def _prepare_frame(self, frame: Any) -> Any:
        pixel_format = str(self.cfg.pixel_format).upper()
        if pixel_format.startswith("RGB") and cv2 is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        flip = str(self.cfg.flip or "none").strip().lower()
        if flip in {"h", "horizontal"}:
            return cv2.flip(frame, 1)
        if flip in {"v", "vertical"}:
            return cv2.flip(frame, 0)
        if flip in {"hv", "both", "180", "rotate180", "r180"}:
            return cv2.flip(frame, -1)
        if flip in {"90", "rotate90", "r90"}:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if flip in {"270", "rotate270", "r270"}:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _notify_metadata(self, metadata: Dict[str, Any]) -> None:
        with self._listeners_lock:
            listeners = list(self._metadata_listeners)
        for listener in listeners:
            try:
                listener(metadata)
            except Exception as exc:
                logger.debug("camera metadata listener failed: %s", exc)

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
