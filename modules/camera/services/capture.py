from __future__ import annotations

import asyncio
import logging
import os
import struct
import subprocess
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


def _find_system_picam_python() -> Optional[str]:
    """Locate a system Python binary (e.g. /usr/bin/python3) that has picamera2 available."""
    candidates = ["/usr/bin/python3", "/usr/bin/python3.13", "/usr/bin/python3.12"]
    for cand in candidates:
        if os.path.isfile(cand) and cand != sys.executable:
            try:
                res = subprocess.run(
                    [cand, "-c", "import picamera2; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and "OK" in res.stdout:
                    return cand
            except Exception:
                pass
    return None


_SYSTEM_PICAM_PYTHON = _find_system_picam_python()
if Picamera2 is None and _SYSTEM_PICAM_PYTHON is not None:
    PICAM_AVAILABLE = True
    PICAM_IMPORT_ERROR = None

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

_BRIDGE_WORKER_CODE = """
import sys
import struct
import time

def main():
    camera_num = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 720
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    quality = int(sys.argv[5]) if len(sys.argv) > 5 else 80
    flip = sys.argv[6].strip().lower() if len(sys.argv) > 6 else 'none'
    pixel_format = sys.argv[7] if len(sys.argv) > 7 else 'RGB888'

    try:
        from picamera2 import Picamera2
        import cv2
    except Exception as exc:
        sys.stderr.write(f"IMPORT_ERROR: {exc}\\n")
        sys.stderr.flush()
        sys.exit(1)

    try:
        picam = Picamera2(camera_num)
        config = picam.create_video_configuration(
            main={"size": (width, height), "format": pixel_format},
            controls={"FrameRate": float(max(1, fps))},
            buffer_count=4,
            queue=True,
        )
        picam.configure(config)
        picam.start()
    except Exception as exc:
        sys.stderr.write(f"CONFIG_ERROR: {exc}\\n")
        sys.stderr.flush()
        sys.exit(2)

    sys.stderr.write("READY\\n")
    sys.stderr.flush()

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, quality)))]

    try:
        while True:
            req = picam.capture_request()
            try:
                frame = req.make_array("main")
                if pixel_format.upper().startswith("RGB"):
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                if flip in ("h", "horizontal"):
                    frame = cv2.flip(frame, 1)
                elif flip in ("v", "vertical"):
                    frame = cv2.flip(frame, 0)
                elif flip in ("hv", "both", "180", "rotate180", "r180"):
                    frame = cv2.flip(frame, -1)
                elif flip in ("90", "rotate90", "r90"):
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif flip in ("270", "rotate270", "r270"):
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if ok:
                    b = encoded.tobytes()
                    sys.stdout.buffer.write(struct.pack(">I", len(b)) + b)
                    sys.stdout.buffer.flush()
            finally:
                req.release()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    except Exception as exc:
        sys.stderr.write(f"LOOP_ERROR: {exc}\\n")
        sys.stderr.flush()
    finally:
        try:
            picam.stop()
            picam.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
"""


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

        # Mode 1: In-process Picamera2
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

        # Mode 2: Picamera2 Subprocess Bridge (via system Python 3.13)
        sys_py = _find_system_picam_python() or _SYSTEM_PICAM_PYTHON
        if sys_py is not None:
            try:
                self._stop.clear()
                self._last_error = ""
                args = [
                    sys_py,
                    "-c",
                    _BRIDGE_WORKER_CODE,
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

        # Mode 3: OpenCV VideoCapture Fallback (V4L2)
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

    def _bridge_capture_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        while not self._stop.is_set():
            try:
                raw_len = stdout.read(4)
                if not raw_len or len(raw_len) < 4:
                    if self._stop.is_set():
                        break
                    time.sleep(0.05)
                    continue
                length = struct.unpack(">I", raw_len)[0]
                data = bytearray()
                while len(data) < length and not self._stop.is_set():
                    chunk = stdout.read(min(4096, length - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                if len(data) == length:
                    self.pub.set_jpeg(bytes(data))
                    self._last_error = ""
            except Exception as exc:
                if not self._stop.is_set():
                    self._last_error = str(exc)
                    logger.warning("Picamera2 bridge read failed: %s", exc)
                    time.sleep(0.1)

    def _cv2_capture_loop(self) -> None:
        assert self._cv2_cap is not None
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, self.cfg.jpeg_quality)))]
        while not self._stop.is_set():
            try:
                ret, frame = self._cv2_cap.read()
                if ret and frame is not None:
                    flip = str(self.cfg.flip or "none").strip().lower()
                    if flip in ("h", "horizontal"):
                        frame = cv2.flip(frame, 1)
                    elif flip in ("v", "vertical"):
                        frame = cv2.flip(frame, 0)
                    elif flip in ("hv", "both", "180", "rotate180", "r180"):
                        frame = cv2.flip(frame, -1)
                    ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                    if ok:
                        self.pub.set_jpeg(encoded.tobytes())
                        self._last_error = ""
                else:
                    time.sleep(0.05)
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("OpenCV capture failed: %s", exc)
                time.sleep(0.1)

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
