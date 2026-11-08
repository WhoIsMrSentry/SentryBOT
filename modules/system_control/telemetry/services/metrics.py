from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import math
import os
import shutil
import threading
from typing import Any, Dict, Optional

from modules.common.runtime_target import read_hardware_pressure

logger = logging.getLogger("telemetry.metrics")

DEFAULT_MAX_EVENT_TYPES = 64
DEFAULT_SUMMARY_WINDOW = 256
_MAX_SUMMARIES = 64


@dataclass
class SystemSnapshot:
    cpu_temp_c: Optional[float] = None
    cpu_load_1m: Optional[float] = None
    mem_available_mb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    disk_used_pct: Optional[float] = None
    pressure_level: Optional[str] = None


def read_system_snapshot(disk_path: str | os.PathLike[str] = ".") -> SystemSnapshot:
    load_1m: Optional[float] = None
    try:
        if hasattr(os, "getloadavg"):
            load_1m = float(os.getloadavg()[0])
    except (AttributeError, OSError) as exc:
        logger.debug("cpu load read unavailable: %s", exc)

    pressure: Dict[str, Any] = {}
    try:
        pressure = read_hardware_pressure()
    except Exception as exc:
        logger.debug("hardware pressure read failed: %s", exc)

    disk_free_gb: Optional[float] = None
    disk_used_pct: Optional[float] = None
    try:
        usage = shutil.disk_usage(disk_path)
        disk_free_gb = round(usage.free / (1024**3), 2)
        if usage.total > 0:
            disk_used_pct = round((usage.used / usage.total) * 100.0, 1)
    except OSError as exc:
        logger.debug("disk usage read failed: %s", exc)

    return SystemSnapshot(
        cpu_temp_c=pressure.get("cpu_temp_c"),
        cpu_load_1m=load_1m,
        mem_available_mb=pressure.get("mem_available_mb"),
        disk_free_gb=disk_free_gb,
        disk_used_pct=disk_used_pct,
        pressure_level=pressure.get("pressure_level"),
    )


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


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return sorted_vals[low]
    frac = pos - low
    return sorted_vals[low] * (1.0 - frac) + sorted_vals[high] * frac


class Summary:
    """Bounded sliding-window numeric summary tracking count, avg, p50, p95 and max."""

    def __init__(
        self,
        name: str,
        doc: str = "",
        max_samples: int = DEFAULT_SUMMARY_WINDOW,
    ) -> None:
        self.name = name
        self.doc = doc
        self._samples: deque[float] = deque(maxlen=max(1, int(max_samples)))
        self._count = 0
        self._sum = 0.0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        val = float(value)
        if not math.isfinite(val):
            return
        with self._lock:
            self._samples.append(val)
            self._count += 1
            self._sum += val

    def stats(self) -> Dict[str, float | int]:
        with self._lock:
            count = self._count
            total = self._sum
            window = list(self._samples)
        if not window:
            return {
                "count": count,
                "sum": round(total, 4),
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "max": 0.0,
            }
        ordered = sorted(window)
        avg = sum(ordered) / len(ordered)
        return {
            "count": count,
            "sum": round(total, 4),
            "avg": round(avg, 4),
            "p50": round(_percentile(ordered, 0.50), 4),
            "p95": round(_percentile(ordered, 0.95), 4),
            "max": round(ordered[-1], 4),
        }


def sanitize_event_name(raw_type: Any) -> str:
    cleaned = str(raw_type or "unknown").replace(" ", "_").replace("-", "_")
    return "".join(c for c in cleaned if c.isalnum() or c == "_")[:32] or "unknown"


class Registry:
    def __init__(self, max_event_types: int = DEFAULT_MAX_EVENT_TYPES) -> None:
        self.counters: Dict[str, Counter] = {}
        self.gauges: Dict[str, Gauge] = {}
        self.summaries: Dict[str, Summary] = {}
        self._event_types: set[str] = set()
        self._max_event_types = max(1, int(max_event_types))
        self._lock = threading.RLock()

    def counter(self, name: str, doc: str = "") -> Counter:
        with self._lock:
            if name not in self.counters:
                self.counters[name] = Counter(name, doc)
            return self.counters[name]

    def gauge(self, name: str, doc: str = "") -> Gauge:
        with self._lock:
            if name not in self.gauges:
                self.gauges[name] = Gauge(name, doc)
            return self.gauges[name]

    def summary(
        self,
        name: str,
        doc: str = "",
        max_samples: int = DEFAULT_SUMMARY_WINDOW,
    ) -> Summary:
        with self._lock:
            if name not in self.summaries:
                if len(self.summaries) >= _MAX_SUMMARIES:
                    return self.summaries.setdefault(
                        "telemetry_other_summary",
                        Summary("telemetry_other_summary", "Overflow summary", max_samples=max_samples),
                    )
                self.summaries[name] = Summary(name, doc, max_samples=max_samples)
            return self.summaries[name]

    def record_event(self, event_type: Any, latency_ms: float | None = None) -> str:
        safe_name = sanitize_event_name(event_type)
        with self._lock:
            self.counter("events_total", "Total recorded telemetry events").inc(1)
            if safe_name in self._event_types or len(self._event_types) < self._max_event_types:
                self._event_types.add(safe_name)
                metric_name = f"event_{safe_name}_total"
                lat_name = f"event_{safe_name}_latency_ms"
            else:
                metric_name = "event_other_total"
                lat_name = "event_other_latency_ms"
            self.counter(metric_name).inc(1)
            if latency_ms is not None and math.isfinite(latency_ms):
                self.summary(lat_name, "Observed event latency in milliseconds").observe(latency_ms)
            return metric_name

    def render_prometheus(self) -> str:
        with self._lock:
            gauges = list(self.gauges.values())
            counters = list(self.counters.values())
            summaries = list(self.summaries.values())
        lines: list[str] = []
        for g in gauges:
            if g.doc:
                lines.append(f"# HELP {g.name} {g.doc}")
            lines.append(f"# TYPE {g.name} gauge")
            lines.append(f"{g.name} {g.value}")
        for c in counters:
            if c.doc:
                lines.append(f"# HELP {c.name} {c.doc}")
            lines.append(f"# TYPE {c.name} counter")
            lines.append(f"{c.name} {c.value}")
        for s in summaries:
            st = s.stats()
            if s.doc:
                lines.append(f"# HELP {s.name} {s.doc}")
            lines.append(f"# TYPE {s.name} summary")
            lines.append(f'{s.name}{{quantile="0.5"}} {st["p50"]}')
            lines.append(f'{s.name}{{quantile="0.95"}} {st["p95"]}')
            lines.append(f'{s.name}{{quantile="1.0"}} {st["max"]}')
            lines.append(f"{s.name}_sum {st['sum']}")
            lines.append(f"{s.name}_count {st['count']}")
        return "\n".join(lines) + "\n"

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            gauges = {g.name: g.value for g in self.gauges.values()}
            counters = {c.name: c.value for c in self.counters.values()}
            summaries = {s.name: s.stats() for s in self.summaries.values()}
            tracked = len(self._event_types)
            max_types = self._max_event_types
        return {
            "gauges": gauges,
            "counters": counters,
            "summaries": summaries,
            "tracked_event_types": tracked,
            "max_event_types": max_types,
        }


REGISTRY = Registry()
