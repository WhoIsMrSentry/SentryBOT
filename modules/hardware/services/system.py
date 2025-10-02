from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import os
import time


def _read_first(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def _cpu_temp_c() -> float | None:
    # Typical path on RPi
    raw = _read_first("/sys/class/thermal/thermal_zone0/temp")
    if raw is None:
        return None
    try:
        val = int(raw)
        # Some kernels expose millidegrees
        return val / 1000.0 if val > 200 else float(val)
    except Exception:
        return None


def _cpu_load() -> float | None:
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            parts = f.read().split()
        return float(parts[0])
    except Exception:
        return None


def _throttled() -> str | None:
    # vcgencmd get_throttled would be ideal; fallback to env indicator
    return os.getenv("RPI_THROTTLED")


@dataclass
class SystemSnapshot:
    timestamp: float
    cpu_temp_c: float | None
    cpu_load_1m: float | None
    throttled: str | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cpu_temp_c": self.cpu_temp_c,
            "cpu_load_1m": self.cpu_load_1m,
            "throttled": self.throttled,
        }


def read_system_snapshot() -> SystemSnapshot:
    return SystemSnapshot(
        timestamp=time.time(),
        cpu_temp_c=_cpu_temp_c(),
        cpu_load_1m=_cpu_load(),
        throttled=_throttled(),
    )
