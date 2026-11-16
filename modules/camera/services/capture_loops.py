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
MAX_BRIDGE_FRAME_BYTES = 16 * 1024 * 1024


def apply_frame_flip(frame: Any, flip: str) -> Any:
    """Apply configured mirror/rotation to a frame, safely no-oping without cv2."""
    if frame is None or cv2 is None:
        return frame
    key = str(flip or "none").strip().lower()
    if key in {"h", "horizontal"}:
        return cv2.flip(frame, 1)
    if key in {"v", "vertical"}:
        return cv2.flip(frame, 0)
    if key in {"hv", "both", "180", "rotate180", "r180"}:
        return cv2.flip(frame, -1)
    if key in {"90", "rotate90", "r90"}:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if key in {"270", "rotate270", "r270"}:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def _read_exact(stream: Any, size: int) -> bytes:
    """Read up to ``size`` bytes from a binary stream, handling partial reads until EOF."""
    buf = bytearray()
    while len(buf) < size:
        chunk = stream.read(size - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


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
        return apply_frame_flip(frame, str(getattr(self.cfg, "flip", "none")))

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
                self.pub.set_raw_frame(frame, quality=int(getattr(self.cfg, "jpeg_quality", 80)))
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
                raw_len = _read_exact(stdout, 4)
                if len(raw_len) < 4:
                    if not self._stop.is_set():
                        rc = self._proc.poll()
                        self._last_error = f"bridge stream EOF (rc={rc})"
                        logger.warning("Picamera2 bridge EOF (rc=%s)", rc)
                    break
                length = struct.unpack(">I", raw_len)[0]
                if length <= 0 or length > MAX_BRIDGE_FRAME_BYTES:
                    self._last_error = f"invalid bridge frame size: {length}"
                    logger.warning("Picamera2 bridge invalid frame length=%d; stopping loop", length)
                    break
                data = _read_exact(stdout, length)
                if len(data) < length:
                    if not self._stop.is_set():
                        rc = self._proc.poll()
                        self._last_error = f"bridge truncated frame ({len(data)}/{length}, rc={rc})"
                    break
                self.pub.set_jpeg(data)
                self._last_error = ""
            except Exception as exc:
                if not self._stop.is_set():
                    self._last_error = str(exc)
                    logger.warning("Picamera2 bridge read failed: %s", exc)
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.1)

    def _cv2_capture_loop(self) -> None:
        assert self._cv2_cap is not None
        flip = str(getattr(self.cfg, "flip", "none"))
        quality = int(getattr(self.cfg, "jpeg_quality", 80))
        while not self._stop.is_set():
            try:
                ret, frame = self._cv2_cap.read()
                if ret and frame is not None:
                    frame = apply_frame_flip(frame, flip)
                    self.pub.set_raw_frame(frame, quality=quality)
                    self._last_error = ""
                else:
                    time.sleep(0.05)
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning("OpenCV capture failed: %s", exc)
                time.sleep(0.1)
