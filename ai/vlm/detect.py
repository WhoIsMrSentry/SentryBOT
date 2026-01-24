"""Lightweight face-focused VLM helpers (YOLO-free).

This module provides reusable helpers for:
- Face candidate detection (OpenCV Haar)
- Descriptor extraction (ORB)
- Identity matching (cv2.FlannBasedMatcher)
- Follow lock (CSRT tracker)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import cv2
import numpy as np

FaceBox = Tuple[int, int, int, int]


@dataclass
class MatchResult:
    name: str
    score: float
    good_matches: int


def detect_faces(frame: np.ndarray, min_size: int = 56) -> List[FaceBox]:
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.12,
        minNeighbors=5,
        minSize=(min_size, min_size),
    )

    h, w = frame.shape[:2]
    out: List[FaceBox] = []
    for (x, y, fw, fh) in faces:
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(w, int(x + fw))
        y2 = min(h, int(y + fh))
        if x2 > x1 and y2 > y1:
            out.append((x1, y1, x2, y2))
    return out


def extract_orb_descriptor(face_roi: np.ndarray, nfeatures: int = 700) -> Optional[np.ndarray]:
    if face_roi is None or not hasattr(face_roi, "shape"):
        return None

    if len(face_roi.shape) == 3:
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = face_roi
    gray = cv2.equalizeHist(gray)
    gray = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)

    orb = cv2.ORB_create(nfeatures=nfeatures)
    _kp, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(desc) == 0:
        return None
    return desc.astype(np.uint8)


def match_with_flann(
    query_descriptor: np.ndarray,
    known: Iterable[Tuple[str, np.ndarray]],
    ratio_test: float = 0.72,
) -> MatchResult:
    """Return best identity match using FLANN-LSH for ORB descriptors."""
    matcher = cv2.FlannBasedMatcher(
        dict(algorithm=6, table_number=6, key_size=12, multi_probe_level=1),
        dict(checks=64),
    )

    best = MatchResult(name="Unknown", score=0.0, good_matches=0)
    for name, known_desc in known:
        if known_desc is None or len(known_desc) == 0:
            continue
        try:
            pairs = matcher.knnMatch(query_descriptor, known_desc, k=2)
        except Exception:
            continue

        good = 0
        total = 0
        for pair in pairs:
            if len(pair) < 2:
                continue
            m, n = pair
            total += 1
            if m.distance < ratio_test * n.distance:
                good += 1
        if total <= 0:
            continue

        score = good / float(total)
        if score > best.score or (abs(score - best.score) < 1e-6 and good > best.good_matches):
            best = MatchResult(name=name, score=score, good_matches=good)

    return best


def create_csrt_tracker() -> Optional[object]:
    if hasattr(cv2, "TrackerCSRT_create"):
        try:
            return cv2.TrackerCSRT_create()
        except Exception:
            pass

    legacy = getattr(cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        try:
            return legacy.TrackerCSRT_create()
        except Exception:
            pass

    return None


def lock_tracker(frame: np.ndarray, bbox: FaceBox) -> Optional[object]:
    tracker = create_csrt_tracker()
    if tracker is None:
        return None

    x1, y1, x2, y2 = bbox
    ok = tracker.init(frame, (x1, y1, x2 - x1, y2 - y1))
    return tracker if ok else None


def update_tracker(tracker: object, frame: np.ndarray) -> Optional[FaceBox]:
    ok, box = tracker.update(frame)
    if not ok or box is None:
        return None
    x, y, w, h = [int(v) for v in box]
    return (x, y, x + w, y + h)


if __name__ == "__main__":
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("camera open failed")

    tracker = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if tracker is None:
            boxes = detect_faces(frame)
            if boxes:
                tracker = lock_tracker(frame, boxes[0])
                x1, y1, x2, y2 = boxes[0]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
        else:
            tracked = update_tracker(tracker, frame)
            if tracked is None:
                tracker = None
            else:
                x1, y1, x2, y2 = tracked
                cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 180, 255), 2)
                cv2.putText(frame, "CSRT", (x1, max(14, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 180, 255), 2)

        cv2.imshow("face-follow-demo", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
