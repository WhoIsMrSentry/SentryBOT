from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

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

_SYSTEM_PICAM_LOCK = threading.Lock()
_SYSTEM_PICAM_PYTHON: Optional[str] = None
_SYSTEM_PICAM_PROBED = False

logger = logging.getLogger("camera.capture")
MetadataListener = Callable[[Dict[str, Any]], None]


def _resolve_system_picam_python() -> Optional[str]:
    """Lazily locate system picamera2 interpreter on first start (avoids import delay)."""
    global _SYSTEM_PICAM_PYTHON, _SYSTEM_PICAM_PROBED, PICAM_AVAILABLE, PICAM_IMPORT_ERROR
    with _SYSTEM_PICAM_LOCK:
        if not _SYSTEM_PICAM_PROBED:
            _SYSTEM_PICAM_PYTHON = find_system_picam_python()
            _SYSTEM_PICAM_PROBED = True
            if Picamera2 is None and _SYSTEM_PICAM_PYTHON is not None:
                PICAM_AVAILABLE = True
                PICAM_IMPORT_ERROR = None
        return _SYSTEM_PICAM_PYTHON


@dataclass
class CaptureConfig:
    size: Tuple[int, int] = (1280, 720)
    pixel_format: str = "RGB888"
    frame_rate: int = 30
    target_fps: int = 30
    backend: str = "picamera2"
    source: Union[int, str] = 0
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
        self._cond = threading.Condition(self._lock)
        self._frame_bytes: Optional[bytes] = None
        self._raw_frame: Optional[Any] = None
        self._jpeg_quality: int = 80
        self._frame_ts = 0.0
        self._frame_count = 0
        self._subscribers = 0

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return self._subscribers

    def acquire_subscriber(self) -> int:
        with self._lock:
            self._subscribers += 1
            return self._subscribers

    def release_subscriber(self) -> int:
        with self._lock:
            if self._subscribers > 0:
                self._subscribers -= 1
            return self._subscribers

    @contextmanager
    def subscriber_session(self) -> Iterator[None]:
        self.acquire_subscriber()
        try:
            yield
        finally:
            self.release_subscriber()

    def wake_all(self) -> None:
        with self._lock:
            self._cond.notify_all()

    def set_raw_frame(self, raw_frame: Any, quality: int = 80) -> None:
        """Store raw numpy array and lazily encode JPEG only when requested."""
        with self._lock:
            self._raw_frame = raw_frame
            self._frame_bytes = None
            self._jpeg_quality = quality
            self._frame_ts = time.time()
            self._frame_count += 1
            self._cond.notify_all()

    def set_jpeg(self, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._frame_bytes = jpeg_bytes
            self._raw_frame = None
            self._frame_ts = time.time()
            self._frame_count += 1
            self._cond.notify_all()

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            if self._frame_bytes is not None:
                return self._frame_bytes
            if self._raw_frame is not None and cv2 is not None:
                try:
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        self._raw_frame,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, self._jpeg_quality)))],
                    )
                    if ok:
                        self._frame_bytes = encoded.tobytes()
                        return self._frame_bytes
                except Exception:
                    pass
            return None

    def wait_for_frame(
        self,
        after_count: int = 0,
        timeout: float = 0.5,
        stop_event: Optional[threading.Event] = None,
    ) -> Tuple[int, Optional[bytes]]:
        deadline = time.monotonic() + max(0.01, float(timeout))
        with self._cond:
            while self._frame_count <= after_count:
                if stop_event is not None and stop_event.is_set():
                    return self._frame_count, None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._frame_count, None
                self._cond.wait(timeout=remaining)
            if stop_event is not None and stop_event.is_set():
                return self._frame_count, None
            return self._frame_count, self.get_jpeg()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "has_frame": (self._frame_bytes is not None) or (self._raw_frame is not None),
                "frame_count": self._frame_count,
                "subscribers": self._subscribers,
                "last_frame_age_s": max(0.0, time.time() - self._frame_ts) if self._frame_ts else None,
            }


class CameraCapture(CaptureLoopsMixin):
    def __init__(self, cfg: CaptureConfig, publisher: FramePublisher) -> None:
        self.cfg = cfg
        self.pub = publisher
        self._state_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
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

    def _effective_fps(self) -> int:
        return max(1, int(getattr(self.cfg, "target_fps", 0) or self.cfg.frame_rate or 30))

    def _drain_bridge_stderr(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return
        try:
            for raw_line in iter(stderr.readline, b""):
                if self._stop.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if "ERROR" in line:
                    self._last_error = line
                    logger.warning("Picamera2 bridge stderr: %s", line)
                else:
                    logger.debug("Picamera2 bridge stderr: %s", line)
        except Exception:
            pass

    def start(self) -> bool:
        with self._state_lock:
            if self.running:
                return True
            assert_raspberry_pi()

            fps = self._effective_fps()
            backend_pref = str(getattr(self.cfg, "backend", "picamera2") or "picamera2").strip().lower()
            try_picam = backend_pref not in {"opencv", "opencv_v4l2", "v4l2", "cv2"}

            if try_picam and Picamera2 is not None:
                if cv2 is None:
                    raise RuntimeError(f"OpenCV JPEG encoder unavailable: {CV2_IMPORT_ERROR}")
                try:
                    camera = Picamera2(int(self.cfg.camera_num))
                    controls = {"FrameRate": float(fps)}
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

            sys_py = _resolve_system_picam_python() if try_picam else None
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
                        str(fps),
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
                    self._stderr_thread = threading.Thread(
                        target=self._drain_bridge_stderr,
                        args=(self._proc,),
                        name="picamera2-bridge-stderr",
                        daemon=True,
                    )
                    self._stderr_thread.start()
                    self._thread = threading.Thread(
                        target=self._bridge_capture_loop,
                        name="picamera2-bridge-capture",
                        daemon=True,
                    )
                    self._thread.start()
                    logger.info("Picamera2 system bridge capture started via %s", sys_py)
                    return True
                except Exception as exc:
                    logger.warning("Picamera2 system bridge start failed: %s; trying cv2...", exc)

            if cv2 is not None:
                source = getattr(self.cfg, "source", None)
                cap_target = int(self.cfg.camera_num) if source in (None, "") else source
                try:
                    cap = cv2.VideoCapture(cap_target)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.size[0])
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.size[1])
                        cap.set(cv2.CAP_PROP_FPS, fps)
                        self._cv2_cap = cap
                        self._stop.clear()
                        self._last_error = ""
                        self._thread = threading.Thread(target=self._cv2_capture_loop, name="cv2-capture", daemon=True)
                        self._thread.start()
                        logger.info("OpenCV VideoCapture started for source %s", cap_target)
                        return True
                    cap.release()
                except Exception as exc:
                    logger.warning("OpenCV VideoCapture start failed: %s", exc)

            if os.environ.get("SENTRYBOT_ALLOW_PC_FALLBACK") == "1" or os.environ.get("SENTRYBOT_PROFILE") in {"pc", "pc-test"}:
                self._last_error = str(PICAM_IMPORT_ERROR or "No suitable camera backend")
                logger.warning("Camera hardware unavailable (PC/WSL fallback mode): %s", self._last_error)
                return False

            raise RuntimeError(f"Picamera2 unavailable: {PICAM_IMPORT_ERROR or 'No suitable camera backend'}")

    def stop(self) -> None:
        with self._state_lock:
            self._stop.set()
            self.pub.wake_all()

            thread = self._thread
            self._thread = None
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

            proc = self._proc
            self._proc = None
            if proc is not None:
                try:
                    if proc.stdout is not None:
                        try:
                            proc.stdout.close()
                        except Exception:
                            pass
                    if proc.stderr is not None:
                        try:
                            proc.stderr.close()
                        except Exception:
                            pass
                    proc.terminate()
                    proc.wait(timeout=1.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            err_thread = self._stderr_thread
            self._stderr_thread = None
            if err_thread and err_thread.is_alive():
                err_thread.join(timeout=1.0)

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

            cap = self._cv2_cap
            self._cv2_cap = None
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def status(self) -> Dict[str, Any]:
        backend = str(getattr(self.cfg, "backend", "picamera2") or "picamera2")
        if self._proc is not None:
            backend = "picamera2_bridge"
        elif self._cv2_cap is not None:
            backend = "opencv_v4l2"
        elif self._picam is not None:
            backend = "picamera2"

        return {
            "backend": backend,
            "camera_num": int(self.cfg.camera_num),
            "source": getattr(self.cfg, "source", self.cfg.camera_num),
            "size": {"width": int(self.cfg.size[0]), "height": int(self.cfg.size[1])},
            "pixel_format": str(self.cfg.pixel_format),
            "frame_rate": self._effective_fps(),
            "jpeg_quality": int(self.cfg.jpeg_quality),
            "running": self.running,
            "gave_up": self.gave_up,
            "picamera2_available": bool(PICAM_AVAILABLE or _SYSTEM_PICAM_PYTHON is not None),
            "picamera2_import_error": PICAM_IMPORT_ERROR,
            "opencv_available": cv2 is not None,
            "opencv_import_error": CV2_IMPORT_ERROR,
            "last_error": self._last_error,
            **self.pub.status(),
        }

    async def mjpeg_generator(self, fps: int):
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        interval = 1.0 / max(1, int(fps))
        last_count = 0
        last_emit = 0.0
        with self.pub.subscriber_session():
            while not self._stop.is_set() and self.running:
                new_count, frame = await asyncio.to_thread(
                    self.pub.wait_for_frame,
                    last_count,
                    min(0.5, interval),
                    self._stop,
                )
                if self._stop.is_set() or not self.running:
                    break
                if frame and new_count > last_count:
                    last_count = new_count
                    yield boundary + frame + b"\r\n"
                    now = time.monotonic()
                    sleep_for = interval - (now - last_emit) if last_emit else 0.0
                    last_emit = now
                    if sleep_for > 0.002:
                        await asyncio.sleep(sleep_for)

    async def snapshot(self) -> Optional[bytes]:
        return await asyncio.to_thread(self.pub.get_jpeg)


__all__ = [
    "CameraCapture",
    "CaptureConfig",
    "FramePublisher",
    "PICAM_AVAILABLE",
    "PICAM_IMPORT_ERROR",
]
