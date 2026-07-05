from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

_CASCADE_FILENAME = "haarcascade_frontalface_default.xml"


def _is_ascii_path(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _copy_to_ascii_temp(src_path: str, logger: logging.Logger) -> Optional[str]:
    if not src_path or not os.path.exists(src_path):
        return None

    try:
        with open(src_path, "rb") as f:
            raw = f.read()
    except Exception as exc:
        logger.warning("Failed to read cascade source file: %s", exc)
        return None

    digest = hashlib.sha1(raw).hexdigest()[:12]
    temp_dir = os.path.join(tempfile.gettempdir(), "sentrybot_cv")
    os.makedirs(temp_dir, exist_ok=True)
    dst_path = os.path.join(temp_dir, f"{digest}_{_CASCADE_FILENAME}")

    if not os.path.exists(dst_path):
        try:
            with open(dst_path, "wb") as f:
                f.write(raw)
        except Exception as exc:
            logger.warning("Failed to write cascade fallback file: %s", exc)
            return None

    return dst_path


def load_frontal_face_cascade(logger: Optional[logging.Logger] = None):
    """Load frontal face cascade with a Windows non-ASCII path fallback."""
    log = logger or logging.getLogger("vlm_bridge.cascade")
    if cv2 is None or not hasattr(cv2, "CascadeClassifier"):
        log.warning("OpenCV not available or CascadeClassifier not supported; face cascade disabled")
        return None

    source_path = os.path.join(cv2.data.haarcascades, _CASCADE_FILENAME)

    candidate_paths = []
    if _is_ascii_path(source_path):
        candidate_paths.append(source_path)
    else:
        fallback_path = _copy_to_ascii_temp(source_path, log)
        if fallback_path:
            candidate_paths.append(fallback_path)
        candidate_paths.append(source_path)

    for candidate in candidate_paths:
        try:
            cascade = cv2.CascadeClassifier(candidate)
            if cascade is not None and not cascade.empty():
                if candidate != source_path:
                    log.info("Loaded Haar cascade via ASCII fallback path: %s", candidate)
                return cascade
        except Exception as exc:
            log.debug("Cascade load failed for '%s': %s", candidate, exc)

    log.warning("Could not load Haar cascade from: %s", source_path)
    return cv2.CascadeClassifier()
