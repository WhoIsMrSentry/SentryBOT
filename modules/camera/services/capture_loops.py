from __future__ import annotations

import logging
import struct
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import cv2
except Exception:
    cv2 = None

logger = logging.getLogger("camera.capture_loops")


class CaptureLoopsMixin:
    """Capture loops for Picamera2 direct, bridge subprocess, and OpenCV."""

    cfg: Any
    pub: Any
    _stop: threading.Event
    _picam: Optional[Any]
    _proc: Optional[Any]
    _cv2_cap: Optional[Any]
    _last_error: str
    _listeners_lock: threading.RLock
    _metadata_listeners: List[Any]

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
