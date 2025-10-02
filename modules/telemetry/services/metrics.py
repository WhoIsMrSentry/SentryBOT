from __future__ import annotations
from typing import Dict
import threading


class Counter:
    def __init__(self, name: str, doc: str = "") -> None:
        self.name = name
        self.doc = doc
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, n: float = 1.0) -> None:
        with self._lock:
            self._value += n

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge(Counter):
    def set(self, v: float) -> None:
        with self._lock:
            self._value = v


class Registry:
    def __init__(self) -> None:
        self.counters: Dict[str, Counter] = {}
        self.gauges: Dict[str, Gauge] = {}

    def counter(self, name: str, doc: str = "") -> Counter:
        if name not in self.counters:
            self.counters[name] = Counter(name, doc)
        return self.counters[name]

    def gauge(self, name: str, doc: str = "") -> Gauge:
        if name not in self.gauges:
            self.gauges[name] = Gauge(name, doc)
        return self.gauges[name]

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for g in self.gauges.values():
            if g.doc:
                lines.append(f"# HELP {g.name} {g.doc}")
            lines.append(f"# TYPE {g.name} gauge")
            lines.append(f"{g.name} {g.value}")
        for c in self.counters.values():
            if c.doc:
                lines.append(f"# HELP {c.name} {c.doc}")
            lines.append(f"# TYPE {c.name} counter")
            lines.append(f"{c.name} {c.value}")
        return "\n".join(lines) + "\n"


REGISTRY = Registry()
