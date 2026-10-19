"""Shared on-sensor hints contract for remote multimodal pairing.

Schema ``onsensor_hints@1``:

    {
        "schema": "onsensor_hints@1",
        "backend": "imx500",
        "model": "ssd_mobilenetv2_fpnlite_320x320_pp",
        "captured_at": "2026-01-01T00:00:00Z",
        "age_s": 0.3,
        "frame": {"w": 1920, "h": 1080},
        "detections": [
            {"label": "person", "confidence": 0.91,
             "bbox_xyxy_norm": [x1n, y1n, x2n, y2n],
             "bbox_xyxy": [x1, y1, x2, y2],
             "track_id": 3,
             "source": "onsensor"}
        ],
    }

Producer (robot, IMX500 bus snapshot) -> consumer (remote multimodal server).
The consumer treats person detections as ground truth and skips its own
overlapping detectors; non-person detections merge into its object list.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Dict, List, Optional, Sequence

HINTS_SCHEMA = "onsensor_hints@1"
HAZARD_LABELS = frozenset({"knife", "fire", "scissors"})


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _utc_iso(ts: float) -> str:
    try:
        dt = datetime.datetime.fromtimestamp(float(ts), tz=datetime.timezone.utc)
    except Exception:
        dt = datetime.datetime.now(tz=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def build_onsensor_hints(
    snapshot: Any,
    frame_shape: Optional[Sequence[int]] = None,
    *,
    max_age_s: float = 1.5,
    model_name: str = "",
) -> Optional[Dict[str, Any]]:
    """Serialize the freshest IMX500 snapshot into hints, or None if stale/empty."""
    if snapshot is None:
        return None
    try:
        ts = float(getattr(snapshot, "ts", 0.0) or 0.0)
    except Exception:
        return None
    now = time.time()
    age_s = now - ts
    if age_s > max_age_s or age_s < -0.5:
        return None

    width = int(getattr(snapshot, "width", 0) or 0)
    height = int(getattr(snapshot, "height", 0) or 0)
    if frame_shape is not None:
        try:
            height, width = int(frame_shape[0]), int(frame_shape[1])
        except Exception:
            pass

    out_dets: List[Dict[str, Any]] = []
    for det in getattr(snapshot, "detections", None) or []:
        if det is None:
            continue
        label = str(getattr(det, "label", "") or "").strip() or "unknown"
        bbox = getattr(det, "bbox_xyxy_norm", None)
        if not bbox or len(bbox) != 4:
            continue
        try:
            x1n, y1n, x2n, y2n = [float(v) for v in bbox]
        except Exception:
            continue
        entry: Dict[str, Any] = {
            "label": label,
            "confidence": round(float(_clamp(float(getattr(det, "score", 0.0) or 0.0), 0.0, 1.0)), 3),
            "bbox_xyxy_norm": [
                _clamp(x1n, 0.0, 1.0),
                _clamp(y1n, 0.0, 1.0),
                _clamp(x2n, 0.0, 1.0),
                _clamp(y2n, 0.0, 1.0),
            ],
            "source": "onsensor",
        }
        try:
            raw_tid = getattr(det, "track_id", None)
            entry["track_id"] = int(raw_tid) if raw_tid is not None else None
        except Exception:
            pass
        if width > 0 and height > 0:
            x1 = int(_clamp(x1n * width, 0, width - 1))
            y1 = int(_clamp(y1n * height, 0, height - 1))
            x2 = int(_clamp(x2n * width, x1 + 1, width))
            y2 = int(_clamp(y2n * height, y1 + 1, height))
            if x2 > x1 and y2 > y1:
                entry["bbox_xyxy"] = [x1, y1, x2, y2]
        out_dets.append(entry)

    hints: Dict[str, Any] = {
        "schema": HINTS_SCHEMA,
        "backend": str(getattr(snapshot, "backend", "") or "imx500"),
        "captured_at": _utc_iso(ts),
        "age_s": round(max(0.0, age_s), 3),
        "detections": out_dets,
    }
    if model_name:
        hints["model"] = str(model_name)
    if width > 0 and height > 0:
        hints["frame"] = {"w": width, "h": height}
    return hints
