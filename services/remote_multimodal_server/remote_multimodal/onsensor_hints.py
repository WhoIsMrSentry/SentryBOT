"""Consumer-side parser for the shared onsensor_hints@1 contract.

Robot (IMX500 bus) -> remote multimodal server. Person detections are treated
as ground truth (identity work stays on-sensor plus robot-side); the server
skips its own overlapping person/face detectors and merges its own object
detections with the non-person hints detections, all source-tagged.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

HINTS_SCHEMA = "onsensor_hints@1"
HAZARD_LABELS = frozenset({"knife", "fire", "scissors"})

_MAX_HINTS_AGE_S = 3.0  # /^ producer clamps 1.5s; allow slight LAN jitter


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def parse_onsensor_hints(
    data: Any,
    frame_h: int = 0,
    frame_w: int = 0,
    *,
    max_age_s: float = _MAX_HINTS_AGE_S,
) -> Optional[Dict[str, Any]]:
    """Validate+normalize hints; returns {"detections": [...], "people": [...], "header": {...}} or None."""
    if not isinstance(data, dict):
        return None
    if str(data.get("schema", "")).strip() != HINTS_SCHEMA:
        return None
    raw_dets = data.get("detections")
    if not isinstance(raw_dets, list):
        return None
    header = {
        "model": str(data.get("model", "") or "").strip(),
        "backend": str(data.get("backend", "") or "").strip() or "imx500",
        "captured_at": str(data.get("captured_at", "") or "").strip(),
    }
    try:
        age_s = float(data.get("age_s", 0.0) or 0.0)
        header["age_s"] = round(max(0.0, age_s), 3)
        stale = age_s > max_age_s
    except Exception:
        stale = False
    if stale:
        return None

    src_w = src_h = 0
    frame = data.get("frame")
    if isinstance(frame, dict):
        try:
            src_w, src_h = int(frame.get("w", 0) or 0), int(frame.get("h", 0) or 0)
        except Exception:
            src_w = src_h = 0

    dets: List[Dict[str, Any]] = []
    people: List[Dict[str, Any]] = []
    for raw in raw_dets:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label", "") or "").strip()
        if not label:
            continue
        try:
            conf = float(_clamp(float(raw.get("confidence", 0.0) or 0.0), 0.0, 1.0))
        except Exception:
            continue
        norm = raw.get("bbox_xyxy_norm")
        if not isinstance(norm, (list, tuple)) or len(norm) != 4:
            continue
        try:
            x1n, y1n, x2n, y2n = [float(v) for v in norm]
        except Exception:
            continue
        if not all(-0.05 <= v <= 1.05 for v in (x1n, y1n, x2n, y2n)):
            continue
        x1n, y1n, x2n, y2n = [
            _clamp(x1n, 0.0, 1.0),
            _clamp(y1n, 0.0, 1.0),
            _clamp(x2n, 0.0, 1.0),
            _clamp(y2n, 0.0, 1.0),
        ]
        det: Dict[str, Any] = {
            "label": label.lower(),
            "confidence": round(conf, 3),
            "bbox_xyxy_norm": [x1n, y1n, x2n, y2n],
            "source": "onsensor",
        }
        try:
            raw_tid = raw.get("track_id")
            det["track_id"] = int(raw_tid) if raw_tid is not None else None
        except Exception:
            det["track_id"] = None
        bbox_xyxy = _denorm(x1n, y1n, x2n, y2n, frame_h, frame_w)
        if bbox_xyxy is None and src_w > 0 and src_h > 0:
            bbox_xyxy = _denorm(x1n, y1n, x2n, y2n, src_h, src_w)
        if bbox_xyxy is not None:
            det["bbox_xyxy"] = list(bbox_xyxy)
        dets.append(det)
        if label.lower() == "person":
            person = dict(det)
            person["label"] = "person"
            people.append(person)
    return {"detections": dets, "people": people, "header": header}


def _denorm(
    x1n: float, y1n: float, x2n: float, y2n: float, h: int, w: int
) -> Optional[Tuple[int, int, int, int]]:
    if h <= 0 or w <= 0:
        return None
    x1 = int(_clamp(x1n * w, 0, w - 1))
    y1 = int(_clamp(y1n * h, 0, h - 1))
    x2 = int(_clamp(x2n * w, x1 + 1, w))
    y2 = int(_clamp(y2n * h, y1 + 1, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def hint_hazard_types(dets: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for det in dets:
        label = str(det.get("label", "")).strip().lower()
        if label in HAZARD_LABELS and label not in seen:
            seen.append(label)
    return seen
