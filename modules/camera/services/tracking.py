from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .onsensor_bus import OnSensorDetection


Box = Tuple[float, float, float, float]


def _iou(a: Box, b: Box) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    label: str
    score: float
    bbox: Box
    first_seen: float
    last_seen: float
    missed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "label": self.label,
            "score": self.score,
            "bbox_xyxy_norm": list(self.bbox),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "age_s": round(max(0.0, time.time() - self.first_seen), 3),
            "missed": self.missed,
        }


class DetectionTracker:
    def __init__(self, iou_threshold: float = 0.3, max_missed: int = 8) -> None:
        self.iou_threshold = float(iou_threshold)
        self.max_missed = int(max_missed)
        self._lock = threading.RLock()
        self._tracks: Dict[int, Track] = {}
        self._next_id = 1
        self._target_label = "person"
        self._target_strategy = "largest"
        self._target_track_id: Optional[int] = None

    def update(self, detections: Iterable[OnSensorDetection]) -> List[OnSensorDetection]:
        now = time.time()
        incoming = list(detections)
        with self._lock:
            unmatched_tracks = set(self._tracks)
            output: List[OnSensorDetection] = []
            for detection in sorted(incoming, key=lambda item: item.score, reverse=True):
                best_id: Optional[int] = None
                best_iou = self.iou_threshold
                for track_id in list(unmatched_tracks):
                    track = self._tracks[track_id]
                    if track.label != detection.label:
                        continue
                    score = _iou(track.bbox, detection.bbox_xyxy_norm)
                    if score >= best_iou:
                        best_iou = score
                        best_id = track_id
                if best_id is None:
                    best_id = self._next_id
                    self._next_id += 1
                    self._tracks[best_id] = Track(
                        track_id=best_id,
                        label=detection.label,
                        score=detection.score,
                        bbox=detection.bbox_xyxy_norm,
                        first_seen=now,
                        last_seen=now,
                    )
                else:
                    unmatched_tracks.discard(best_id)
                    track = self._tracks[best_id]
                    track.score = detection.score
                    track.bbox = detection.bbox_xyxy_norm
                    track.last_seen = now
                    track.missed = 0
                output.append(
                    OnSensorDetection(
                        class_id=detection.class_id,
                        label=detection.label,
                        score=detection.score,
                        bbox_xyxy_norm=detection.bbox_xyxy_norm,
                        track_id=best_id,
                    )
                )

            for track_id in unmatched_tracks:
                self._tracks[track_id].missed += 1
            self._tracks = {track_id: track for track_id, track in self._tracks.items() if track.missed <= self.max_missed}
            if self._target_track_id not in self._tracks:
                self._target_track_id = None
            return output

    def select(self, label: str = "person", strategy: str = "largest", track_id: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            self._target_label = str(label or "person").strip().lower()
            self._target_strategy = str(strategy or "largest").strip().lower()
            self._target_track_id = int(track_id) if track_id is not None else None
            target = self._select_locked()
            return {"ok": target is not None, "selection": self.selection(), "target": target.to_dict() if target else None}

    def selection(self) -> Dict[str, Any]:
        return {
            "label": self._target_label,
            "strategy": self._target_strategy,
            "track_id": self._target_track_id,
        }

    def target(self) -> Optional[Track]:
        with self._lock:
            return self._select_locked()

    def tracks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [track.to_dict() for track in sorted(self._tracks.values(), key=lambda item: item.track_id)]

    def _select_locked(self) -> Optional[Track]:
        if self._target_track_id is not None:
            return self._tracks.get(self._target_track_id)
        candidates = [track for track in self._tracks.values() if track.label.lower() == self._target_label]
        if not candidates:
            return None
        if self._target_strategy == "confidence":
            return max(candidates, key=lambda item: item.score)
        if self._target_strategy == "center":
            return min(candidates, key=lambda item: abs(((item.bbox[0] + item.bbox[2]) / 2.0) - 0.5) + abs(((item.bbox[1] + item.bbox[3]) / 2.0) - 0.5))
        return max(candidates, key=lambda item: max(0.0, item.bbox[2] - item.bbox[0]) * max(0.0, item.bbox[3] - item.bbox[1]))


__all__ = ["DetectionTracker", "Track"]
