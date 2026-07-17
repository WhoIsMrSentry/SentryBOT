from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("camera.onsensor_bus")


@dataclass
class OnSensorDetection:
    class_id: int
    label: str
    score: float
    bbox_xyxy_norm: Tuple[float, float, float, float]
    track_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["bbox_xyxy_norm"] = list(self.bbox_xyxy_norm)
        return data


@dataclass
class OnSensorSnapshot:
    ts: float = field(default_factory=time.time)
    frame_id: int = 0
    width: int = 0
    height: int = 0
    detections: List[OnSensorDetection] = field(default_factory=list)
    backend: str = "imx500"
    target_track_id: Optional[int] = None
    target_label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "frame_id": self.frame_id,
            "width": self.width,
            "height": self.height,
            "backend": self.backend,
            "target_track_id": self.target_track_id,
            "target_label": self.target_label,
            "detections": [detection.to_dict() for detection in self.detections],
        }


SubscriberFn = Callable[[OnSensorSnapshot], None]


class OnSensorEventBus:
    def __init__(self, history_size: int = 16) -> None:
        self._lock = threading.RLock()
        self._latest: Optional[OnSensorSnapshot] = None
        self._history: List[OnSensorSnapshot] = []
        self._history_size = max(1, int(history_size))
        self._subscribers: List[SubscriberFn] = []
        self._published_count = 0

    def publish(self, snapshot: OnSensorSnapshot) -> None:
        with self._lock:
            self._latest = snapshot
            self._history.append(snapshot)
            self._history = self._history[-self._history_size :]
            self._published_count += 1
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(snapshot)
            except Exception as exc:
                logger.debug("on-sensor subscriber failed: %s", exc)

    def latest(self) -> Optional[OnSensorSnapshot]:
        with self._lock:
            return self._latest

    def history(self) -> List[OnSensorSnapshot]:
        with self._lock:
            return list(self._history)

    def subscribe(self, subscriber: SubscriberFn) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "published_count": self._published_count,
                "history_size": len(self._history),
                "subscribers": len(self._subscribers),
                "has_latest": self._latest is not None,
            }


_default_bus: Optional[OnSensorEventBus] = None
_default_lock = threading.RLock()


def get_default_bus() -> OnSensorEventBus:
    global _default_bus
    with _default_lock:
        if _default_bus is None:
            _default_bus = OnSensorEventBus()
        return _default_bus


def set_default_bus(bus: Optional[OnSensorEventBus]) -> None:
    global _default_bus
    with _default_lock:
        _default_bus = bus


__all__ = ["OnSensorDetection", "OnSensorSnapshot", "OnSensorEventBus", "get_default_bus", "set_default_bus"]
