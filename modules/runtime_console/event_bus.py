from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Iterable


@dataclass(frozen=True)
class RuntimeEvent:
    channel: str
    message: str
    level: str = "INFO"
    status: str = "INFO"
    trace_id: str | None = None
    component: str | None = None
    reason: str | None = None
    duration_ms: int | None = None
    created_at: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)


class RuntimeEventBus:
    def __init__(self, maxlen: int = 200) -> None:
        self._events: Deque[RuntimeEvent] = deque(maxlen=maxlen)
        self._lock = threading.RLock()

    def publish(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._events.append(event)

    def tail(self, limit: int = 20) -> list[RuntimeEvent]:
        with self._lock:
            if limit <= 0:
                return []
            events = list(self._events)
            return events[-limit:]

    def iter(self) -> Iterable[RuntimeEvent]:
        with self._lock:
            return tuple(self._events)


_BUS = RuntimeEventBus()


def get_event_bus() -> RuntimeEventBus:
    return _BUS


def publish_event(
    channel: str,
    message: str,
    *,
    level: str = "INFO",
    status: str = "INFO",
    trace_id: str | None = None,
    component: str | None = None,
    reason: str | None = None,
    duration_ms: int | None = None,
    **details: Any,
) -> RuntimeEvent:
    event = RuntimeEvent(
        channel=channel.upper(),
        message=message,
        level=level.upper(),
        status=status.upper(),
        trace_id=trace_id,
        component=component,
        reason=reason,
        duration_ms=duration_ms,
        details=details,
    )
    _BUS.publish(event)
    return event
