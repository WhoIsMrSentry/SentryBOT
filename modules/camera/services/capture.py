from __future__ import annotations
import asyncio
import threading
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import cv2
except Exception as e:
    cv2 = None  # OpenCV not available (or missing libGL etc.)

try:
    from picamera2 import Picamera2  # type: ignore
    PICAM_AVAILABLE = True
except Exception:
    PICAM_AVAILABLE = False


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
        self._cap: Optional[cv2.VideoCapture] = None
        self._picam: Optional["Picamera2"] = None

    def _start_opencv(self) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV (cv2) not available: check libGL (libGL.so.1) and opencv-python installation")
        src = self.cfg.source if isinstance(self.cfg.source, (int, str)) else 0
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW if isinstance(src, int) else 0)
        w, h = self.cfg.resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*self.cfg.opencv_fourcc))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.cfg.opencv_buffer_size)
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
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
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
        cam = Picamera2()
        w, h = self.cfg.picam_size
        cam.configure(cam.create_video_configuration(
            main={"size": (w, h), "format": self.cfg.picam_format},
            controls={"AfMode": self.cfg.picam_af_mode, "FrameRate": self.cfg.picam_frame_rate}
        ))
        cam.start()
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
            while not self._stop.is_set():
                rgb = cam.capture_array("main")
                rgb = _apply_flip(rgb)
                ok, buf = cv2.imencode('.jpg', rgb, [cv2.IMWRITE_JPEG_QUALITY, q])
                if ok:
                    self.pub.set_jpeg(buf.tobytes())
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def start(self) -> None:
        backend = self.cfg.backend
        if backend == "auto":
            backend = "picamera2" if PICAM_AVAILABLE else "opencv"
        if backend == "picamera2":
            self._start_picam()
        else:
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
