from __future__ import annotations

import fnmatch
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class RobotEvent:
    topic: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    priority: int = 50
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": dict(self.payload),
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.timestamp,
        }


class RobotEventBus:
    """Thread-safe in-process pub/sub event backbone with wildcard support and bounded history."""

    def __init__(self, maxlen: int = 256) -> None:
        self._lock = threading.RLock()
        self._history: Deque[RobotEvent] = deque(maxlen=max(1, int(maxlen)))
        self._subscribers: Dict[str, Tuple[str, Callable[[RobotEvent], None]]] = {}

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        pat = str(pattern or "").strip()
        top = str(topic or "").strip()
        if not pat or not top:
            return False
        if pat == "*" or pat == top:
            return True
        if pat.endswith(".*"):
            prefix = pat[:-2]
            if top == prefix or top.startswith(prefix + "."):
                return True
        return fnmatch.fnmatchcase(top, pat)

    def subscribe(
        self,
        topic_pattern: str,
        callback: Callable[[RobotEvent], None],
    ) -> str:
        if not callable(callback):
            raise TypeError("callback must be callable")
        pattern = str(topic_pattern or "*").strip() or "*"
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._subscribers[sub_id] = (pattern, callback)
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        with self._lock:
            return self._subscribers.pop(str(sub_id or ""), None) is not None

    def publish(
        self,
        topic: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        source: str = "system",
        priority: int = 50,
    ) -> RobotEvent:
        clean_topic = str(topic or "").strip()
        event = RobotEvent(
            topic=clean_topic,
            payload=dict(payload) if isinstance(payload, dict) else {},
            source=str(source or "system"),
            priority=int(priority),
            timestamp=time.time(),
        )
        with self._lock:
            self._history.append(event)
            matching_callbacks = [
                cb
                for pat, cb in self._subscribers.values()
                if self._matches(pat, clean_topic)
            ]
        for cb in matching_callbacks:
            try:
                cb(event)
            except Exception:
                pass
        return event

    def recent(self, topic_prefix: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        prefix = str(topic_prefix or "").strip()
        if prefix.endswith("*"):
            prefix = prefix[:-1]
        max_items = max(0, int(limit))
        if max_items == 0:
            return []
        with self._lock:
            items = [
                ev.to_dict()
                for ev in self._history
                if not prefix or ev.topic.startswith(prefix)
            ]
        return items[-max_items:]

    def recent_events(self, topic_prefix: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        return self.recent(topic_prefix=topic_prefix, limit=limit)

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)


_BUS_LOCK = threading.Lock()
_ROBOT_EVENT_BUS: Optional[RobotEventBus] = None


def get_robot_event_bus() -> RobotEventBus:
    global _ROBOT_EVENT_BUS
    with _BUS_LOCK:
        if _ROBOT_EVENT_BUS is None:
            _ROBOT_EVENT_BUS = RobotEventBus()
        return _ROBOT_EVENT_BUS


def reset_robot_event_bus() -> None:
    global _ROBOT_EVENT_BUS
    with _BUS_LOCK:
        _ROBOT_EVENT_BUS = RobotEventBus()
