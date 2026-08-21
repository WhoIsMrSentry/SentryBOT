from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import os
from pathlib import Path
import threading


@dataclass
class SystemSnapshot:
    cpu_temp_c: Optional[float] = None
    cpu_load_1m: Optional[float] = None


def read_system_snapshot() -> SystemSnapshot:
    temp_c = None
    load_1m = None
    try:
        if hasattr(os, "getloadavg"):
            load_1m = float(os.getloadavg()[0])
    except Exception:
        pass
    try:
        thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal_path.exists():
            temp_c = float(thermal_path.read_text().strip()) / 1000.0
    except Exception:
        pass
    return SystemSnapshot(cpu_temp_c=temp_c, cpu_load_1m=load_1m)


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
