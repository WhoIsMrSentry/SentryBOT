from __future__ import annotations
import asyncio
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

try:
    import cv2
except Exception as e:
    cv2 = None  # OpenCV not available (or missing libGL etc.)

PICAM_AVAILABLE = False
PICAM_IMPORT_ERROR: Optional[str] = None

try:
    from picamera2 import Picamera2  # type: ignore
    PICAM_AVAILABLE = True
except Exception as exc:
    PICAM_IMPORT_ERROR = repr(exc)
    # Some virtualenv setups on Raspberry Pi miss system dist-packages in sys.path.
    for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3/dist-packages"):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    try:
        from picamera2 import Picamera2  # type: ignore
        PICAM_AVAILABLE = True
        PICAM_IMPORT_ERROR = None
    except Exception as exc2:
        PICAM_AVAILABLE = False
        PICAM_IMPORT_ERROR = repr(exc2)


logger = logging.getLogger("camera.capture")


@dataclass
class CaptureConfig:
    backend: str  # auto|picamera2|opencv
    source: object  # int index or str URL
    resolution: Tuple[int, int]
    fps_target: int
    jpeg_quality: int
    opencv_fourcc: str
    opencv_buffer_size: int
    picam_size: Tuple[int, int]
    picam_format: str
    picam_frame_rate: int
    picam_af_mode: int
    flip: str
    opencv_max_open_attempts: int = 5
    opencv_retry_interval_s: float = 1.0


class FramePublisher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame_bytes: Optional[bytes] = None

    def set_jpeg(self, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._frame_bytes = jpeg_bytes

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._frame_bytes


class CameraCapture:
    def __init__(self, cfg: CaptureConfig, publisher: FramePublisher) -> None:
        self.cfg = cfg
        self.pub = publisher
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[Any] = None
        self._picam: Optional["Picamera2"] = None
        self._gave_up = False

    @property
    def gave_up(self) -> bool:
        return self._gave_up

    def _opencv_api_candidates(self, src: object) -> list[Optional[int]]:
        if cv2 is None or not isinstance(src, int):
            return [None]

        # CAP_DSHOW is Windows-only; on Linux/RPi prefer V4L2/CAP_ANY.
        if os.name == "nt":
            return [getattr(cv2, "CAP_DSHOW", None), getattr(cv2, "CAP_ANY", None), None]
        return [getattr(cv2, "CAP_V4L2", None), getattr(cv2, "CAP_ANY", None), None]

    def _opencv_source_candidates(self, src: object) -> list[Tuple[object, Optional[int]]]:
        candidates: list[Tuple[object, Optional[int]]] = [(src, None)]
        if cv2 is None:
            return candidates

        if isinstance(src, int) and os.name != "nt":
            # Prefer explicit V4L2 device path as secondary candidate on Linux.
            candidates.append((f"/dev/video{src}", None))

            # Last resort: libcamera GStreamer pipeline (when OpenCV has GStreamer support).
            gst_api = getattr(cv2, "CAP_GSTREAMER", None)
            if gst_api is not None:
                w, h = self.cfg.resolution
                fps = max(5, min(60, int(self.cfg.fps_target or 30)))
                gst_pipeline = (
                    f"libcamerasrc ! video/x-raw,width={w},height={h},framerate={fps}/1 ! "
                    "videoconvert ! appsink drop=true sync=false"
                )
                candidates.append((gst_pipeline, gst_api))

        return candidates

    def _configure_opencv_capture(self, cap: Any) -> None:
        w, h = self.cfg.resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*self.cfg.opencv_fourcc))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.cfg.opencv_buffer_size)

    def _open_opencv_capture(self, src: object) -> Tuple[Optional[Any], str]:
        if cv2 is None:
            return None, "cv2-unavailable"

        for candidate_src, forced_api in self._opencv_source_candidates(src):
            api_candidates = [forced_api] if forced_api is not None else self._opencv_api_candidates(candidate_src)
            for api in api_candidates:
                try:
                    cap = cv2.VideoCapture(candidate_src) if api is None else cv2.VideoCapture(candidate_src, api)
                except Exception:
                    continue

                if cap is None or not cap.isOpened():
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                    continue

                self._configure_opencv_capture(cap)

                # Some backends report opened but never deliver frames; validate quickly.
                ok = False
                frame = None
                for _ in range(3):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        break
                    time.sleep(0.05)

                if ok and frame is not None:
                    api_name = "default" if api is None else str(api)
                    return cap, f"{api_name}|src={candidate_src!r}"

                try:
                    cap.release()
                except Exception:
                    pass

        return None, "none"

    def _start_opencv(self) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV (cv2) not available: check libGL (libGL.so.1) and opencv-python installation")
        src = self.cfg.source if isinstance(self.cfg.source, (int, str)) else 0
        cap, api_name = self._open_opencv_capture(src)
        self._cap = cap

        def _apply_flip(img):
            f = (self.cfg.flip or "none").strip().lower()
            if not f or f == "none":
                return img
            if f in ("h", "horizontal"):
                return cv2.flip(img, 1)
            if f in ("v", "vertical"):
                return cv2.flip(img, 0)
            if f in ("hv", "both", "180", "rotate180", "r180"):
                return cv2.flip(img, -1)
            if f in ("90", "rotate90", "r90"):
                return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            if f in ("270", "rotate270", "r270"):
                return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            try:
                deg = int(f)
                d = deg % 360
                if d == 90:
                    return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                if d == 180:
                    return cv2.flip(img, -1)
                if d == 270:
                    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            except Exception:
                pass
            return img

        def loop() -> None:
            q = self.cfg.jpeg_quality
            open_fail_count = 0
            max_attempts = max(1, int(self.cfg.opencv_max_open_attempts))
            retry_s = max(0.2, float(self.cfg.opencv_retry_interval_s))
            nonlocal cap, api_name
            while not self._stop.is_set():
                if cap is None or not cap.isOpened():
                    cap, api_name = self._open_opencv_capture(src)
                    self._cap = cap
                    if cap is None:
                        open_fail_count += 1
                        if open_fail_count >= max_attempts:
                            if not self._gave_up:
                                self._gave_up = True
                                logger.warning(
                                    "OpenCV camera unavailable after %d attempts (source=%r); stopping retries",
                                    max_attempts,
                                    src,
                                )
                            break
                        if open_fail_count == 1 or open_fail_count == max_attempts:
                            logger.warning(
                                "OpenCV camera source not ready: source=%r attempt=%d/%d",
                                src,
                                open_fail_count,
                                max_attempts,
                            )
                        time.sleep(retry_s)
                        continue

                    open_fail_count = 0
                    logger.info("OpenCV camera connected: source=%r api=%s", src, api_name)

                ok, frame = cap.read()
                if not ok:
                    logger.warning("OpenCV camera read failed, reconnecting source=%r", src)
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    self._cap = None
                    time.sleep(0.4)
                    continue
                frame = _apply_flip(frame)
                ok2, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, q])
                if ok2:
                    self.pub.set_jpeg(buf.tobytes())
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def _start_picam(self) -> None:
        if not PICAM_AVAILABLE:
            raise RuntimeError("Picamera2 not available")
        if cv2 is None:
            raise RuntimeError("OpenCV (cv2) is required for JPEG encoding with picamera2 backend")
        cam = Picamera2()
        try:
            w, h = self.cfg.picam_size
            cam.configure(cam.create_video_configuration(
                main={"size": (w, h), "format": self.cfg.picam_format},
                controls={"AfMode": self.cfg.picam_af_mode, "FrameRate": self.cfg.picam_frame_rate}
            ))
            cam.start()
        except Exception:
            try:
                cam.close()
            except Exception:
                pass
            raise
        self._picam = cam

        def _apply_flip(img):
            f = (self.cfg.flip or "none").strip().lower()
            if not f or f == "none":
                return img
            if f in ("h", "horizontal"):
                return cv2.flip(img, 1)
            if f in ("v", "vertical"):
                return cv2.flip(img, 0)
            if f in ("hv", "both", "180", "rotate180", "r180"):
                return cv2.flip(img, -1)
            if f in ("90", "rotate90", "r90"):
                return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            if f in ("270", "rotate270", "r270"):
                return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            try:
                deg = int(f)
                d = deg % 360
                if d == 90:
                    return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                if d == 180:
                    return cv2.flip(img, -1)
                if d == 270:
                    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            except Exception:
                pass
            return img

        def loop() -> None:
            q = self.cfg.jpeg_quality
            err_count = 0
            while not self._stop.is_set():
                try:
                    rgb = cam.capture_array("main")
                    rgb = _apply_flip(rgb)
                    ok, buf = cv2.imencode('.jpg', rgb, [cv2.IMWRITE_JPEG_QUALITY, q])
                    if ok:
                        self.pub.set_jpeg(buf.tobytes())
                    err_count = 0
                except Exception as exc:
                    err_count += 1
                    if err_count == 1 or (err_count % 20) == 0:
                        logger.warning("Picamera2 frame capture failed (count=%d): %s", err_count, exc)
                    time.sleep(0.2)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def start(self) -> None:
        self._stop.clear()
        backend = self.cfg.backend
        if backend == "auto":
            backend = "picamera2" if PICAM_AVAILABLE else "opencv"
        if backend == "opencv" and os.name != "nt" and isinstance(self.cfg.source, int) and not PICAM_AVAILABLE:
            logger.warning(
                "picamera2 unavailable (error=%s). CSI camera with OpenCV source=%r may fail to deliver frames.",
                PICAM_IMPORT_ERROR,
                self.cfg.source,
            )
        logger.info("CameraCapture starting backend=%s source=%r picam_available=%s", backend, self.cfg.source, PICAM_AVAILABLE)
        if backend == "picamera2":
            try:
                self._start_picam()
                return
            except Exception as exc:
                logger.warning(
                    "picamera2 start failed (%s); falling back to opencv source=%r",
                    exc,
                    self.cfg.source,
                )
        self._start_opencv()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        if self._picam is not None:
            try:
                self._picam.stop()
                self._picam.close()
            except Exception:
                pass

    async def mjpeg_generator(self, fps: int):
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        next_tick = 0.0
        while True:
            if next_tick == 0.0:
                next_tick = asyncio.get_running_loop().time()
            next_tick += 1 / max(1, fps)
            await asyncio.sleep(max(0.0, next_tick - asyncio.get_running_loop().time()))
            frame = await asyncio.to_thread(self.pub.get_jpeg)
            if frame:
                yield boundary + frame + b"\r\n"

    async def snapshot(self) -> Optional[bytes]:
        return await asyncio.to_thread(self.pub.get_jpeg)
