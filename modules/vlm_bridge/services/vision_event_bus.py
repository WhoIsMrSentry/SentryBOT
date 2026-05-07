"""Vision event bus for SentryBOT.

Central pub/sub for visual events so multiple subsystems (Autonomy,
AgentCore, HeadControlArbiter) can react without tight coupling.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger("vlm_bridge.event_bus")

# Standard event types
EVENT_PERSON_SEEN = "person_seen"
EVENT_OWNER_SEEN = "owner_seen"
EVENT_NEW_PERSON = "new_person"
EVENT_HAZARD_DETECTED = "hazard_detected"
EVENT_SCENE_CHANGED = "scene_changed"
EVENT_VLM_RESULT_READY = "vlm_result_ready"
EVENT_FOLLOW_START = "follow_start"
EVENT_FOLLOW_STOP = "follow_stop"
EVENT_PERSON_LOST = "person_lost"

ALL_EVENTS = frozenset({
    EVENT_PERSON_SEEN, EVENT_OWNER_SEEN, EVENT_NEW_PERSON,
    EVENT_HAZARD_DETECTED, EVENT_SCENE_CHANGED, EVENT_VLM_RESULT_READY,
    EVENT_FOLLOW_START, EVENT_FOLLOW_STOP, EVENT_PERSON_LOST,
})

EventHandler = Callable[[str, Dict[str, Any]], None]


class VisionEventBus:
    """Thread-safe publish/subscribe bus for vision events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._global_subscribers: List[EventHandler] = []
        self._event_count: int = 0

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        with self._lock:
            self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event_type: str, data: Dict[str, Any] = None) -> None:
        data = data or {}
        data["event_type"] = event_type
        self._event_count += 1

        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
            global_handlers = list(self._global_subscribers)

        for handler in handlers + global_handlers:
            try:
                handler(event_type, data)
            except Exception as exc:
                logger.warning("Event handler error for '%s': %s", event_type, exc)

    @property
    def event_count(self) -> int:
        return self._event_count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_events": self._event_count,
                "subscribers": {k: len(v) for k, v in self._subscribers.items()},
                "global_subscribers": len(self._global_subscribers),
            }


__all__ = [
    "VisionEventBus",
    "EVENT_PERSON_SEEN", "EVENT_OWNER_SEEN", "EVENT_NEW_PERSON",
    "EVENT_HAZARD_DETECTED", "EVENT_SCENE_CHANGED", "EVENT_VLM_RESULT_READY",
    "EVENT_FOLLOW_START", "EVENT_FOLLOW_STOP", "EVENT_PERSON_LOST",
]
