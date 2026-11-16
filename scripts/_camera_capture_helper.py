"""Shared camera capture helper for SentryBOT face enrollment and verification scripts."""

from __future__ import annotations

import sys
import time
import urllib.request
from typing import Any, Callable, Optional, Tuple


def resolve_gateway_snap_url(explicit_url: Optional[str] = None) -> str:
    """Resolve the active gateway's `/camera/snap` URL using gateway/env config."""
    if explicit_url:
        base = explicit_url.rstrip("/")
        return base if base.endswith("/camera/snap") else f"{base}/camera/snap"
    try:
        from modules.common.url_utils import resolve_gateway_base_url

        base = resolve_gateway_base_url(port=8080).rstrip("/")
    except Exception:
        base = "http://127.0.0.1:8080"
    return f"{base}/camera/snap"


def fetch_frame_from_gateway(snap_url: Optional[str] = None, timeout_s: float = 1.5) -> Any | None:
    """Attempt to grab a single JPEG frame from a running Gateway instance."""
    import cv2
    import numpy as np

    url = resolve_gateway_snap_url(snap_url)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if getattr(resp, "status", 200) == 200:
                raw_bytes = resp.read()
                if raw_bytes:
                    return cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    return None


def capture_live_face_frame(
    *,
    camera_num: int = 0,
    gateway_url: Optional[str] = None,
    max_attempts: int = 30,
    poll_interval_s: float = 0.16,
    frame_selector: Optional[Callable[[Any], Tuple[bool, float]]] = None,
    prefer_gateway: bool = True,
) -> Any | None:
    """Capture a camera frame cleanly with Gateway -> CameraCapture -> OpenCV fallback.

    All camera handles are guaranteed to stop/release in `finally:` blocks.
    `frame_selector(candidate) -> (is_good, score)` allows callers like enroll/verify
    to either stop early when a crisp face match is seen or pick the highest-scored frame.
    """
    import cv2
    import numpy as np

    if prefer_gateway:
        gw_frame = fetch_frame_from_gateway(gateway_url)
        if gw_frame is not None:
            print("[INFO] Captured live frame from running SentryBOT Gateway.")
            return gw_frame

    best_frame: Any = None
    best_score: float = -1.0

    # Standalone Picamera2 / CameraCapture bridge with strict cleanup
    try:
        from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher

        cfg = CaptureConfig(camera_num=camera_num, size=(1280, 720), frame_rate=15)
        pub = FramePublisher()
        cap = CameraCapture(cfg=cfg, publisher=pub)
        if cap.start():
            try:
                for _i in range(1, max_attempts):
                    time.sleep(poll_interval_s)
                    jpeg_bytes = pub.get_jpeg()
                    if not jpeg_bytes:
                        continue
                    candidate = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if candidate is None:
                        continue
                    if frame_selector is None:
                        return candidate
                    accepted, score = frame_selector(candidate)
                    if score > best_score or best_frame is None:
                        best_score = score
                        best_frame = candidate
                    if accepted:
                        return best_frame
                    sys.stdout.write(".")
                    sys.stdout.flush()
            finally:
                cap.stop()
                print()
    except Exception as exc:
        print(f"[WARN] CameraCapture bridge fallback: {exc}")

    if best_frame is not None:
        return best_frame

    # Fallback to direct OpenCV VideoCapture with guaranteed release
    vcap = None
    try:
        vcap = cv2.VideoCapture(camera_num)
        if vcap.isOpened():
            for _ in range(10):
                vcap.read()
            ok, cv_frame = vcap.read()
            if ok and cv_frame is not None:
                return cv_frame
    except Exception as exc:
        print(f"[WARN] OpenCV VideoCapture fallback: {exc}")
    finally:
        if vcap is not None and hasattr(vcap, "release"):
            try:
                vcap.release()
            except Exception:
                pass

    return None
