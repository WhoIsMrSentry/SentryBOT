from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import os
import time
from typing import Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore

_PREFERRED_TEMP_SENSORS = ("cpu_thermal", "coretemp", "k10temp", "acpitz", "soc_thermal")


@dataclass
class SysMetrics:
    cpu_temp: Optional[float] = None
    cpu_load: Optional[float] = None  # 0..1
    net_mbps: Optional[float] = None
    arduino_connected: Optional[bool] = None


def _extract_sensor_temp(entry: object) -> Optional[float]:
    val = getattr(entry, "current", None)
    if val is None:
        val = getattr(entry, "temp", None)
    if val is None:
        return None
    f = float(val)
    return f if math.isfinite(f) else None


class MetricsCollector:
    def __init__(self, window_s: int = 60) -> None:
        self.window_s = max(1, int(window_s))
        self._last_net: Optional[int] = None
        self._last_time: Optional[float] = None
        self._load_samples: deque[tuple[float, float]] = deque()

    def _window_cpu_load(self, instant_load: Optional[float]) -> Optional[float]:
        now = time.monotonic()
        cutoff = now - float(self.window_s)
        while self._load_samples and self._load_samples[0][0] < cutoff:
            self._load_samples.popleft()
        if instant_load is not None and math.isfinite(instant_load):
            clamped = max(0.0, min(1.0, float(instant_load)))
            self._load_samples.append((now, clamped))
        if not self._load_samples:
            return None
        return sum(val for _, val in self._load_samples) / float(len(self._load_samples))

    def sample(self) -> SysMetrics:
        m = SysMetrics()
        instant_load: Optional[float] = None
        snap = self._hardware_snapshot()
        if snap is not None:
            m.cpu_temp = snap.get("cpu_temp_c")
            load = snap.get("cpu_load_1m")
            if load is not None:
                nproc = float(os.cpu_count() or 1)
                instant_load = min(1.0, max(0.0, float(load) / nproc))
        if m.cpu_temp is None:
            m.cpu_temp = self._read_cpu_temp()
        if instant_load is None:
            instant_load = self._read_cpu_load()
        m.cpu_load = self._window_cpu_load(instant_load)
        m.net_mbps = self._read_net_speed_mbps()
        return m

    @staticmethod
    def _hardware_snapshot() -> Optional[dict]:
        snap: dict = {}
        try:
            snap["cpu_load_1m"] = float(os.getloadavg()[0])
        except Exception:
            pass
        temp = MetricsCollector._read_cpu_temp()
        if temp is not None:
            snap["cpu_temp_c"] = temp
        return snap or None

    @staticmethod
    def _read_cpu_temp() -> Optional[float]:
        if psutil is not None and hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures() or {}
                for key in _PREFERRED_TEMP_SENSORS:
                    arr = temps.get(key)
                    if arr:
                        val = _extract_sensor_temp(arr[0])
                        if val is not None:
                            return val
                for _, arr in temps.items():
                    if arr:
                        val = _extract_sensor_temp(arr[0])
                        if val is not None:
                            return val
            except Exception:
                pass
        # Fallback for Linux thermal zone
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
                val = f.read().strip()
                return float(val) / 1000.0
        except Exception:
            return None

    def _read_cpu_load(self) -> Optional[float]:
        if psutil is None:
            return None
        try:
            return float(psutil.cpu_percent(interval=None)) / 100.0
        except Exception:
            return None

    def _read_net_speed_mbps(self) -> Optional[float]:
        if psutil is None:
            return None
        try:
            now = time.monotonic()
            counters = psutil.net_io_counters()
            if counters is None:
                return None
            bytes_total = counters.bytes_recv + counters.bytes_sent
            if self._last_net is None or self._last_time is None:
                self._last_net = bytes_total
                self._last_time = now
                return 0.0
            dt = max(1e-6, now - self._last_time)
            db = max(0, bytes_total - self._last_net)
            mbps = (db * 8.0 / 1_000_000.0) / dt
            self._last_net = bytes_total
            self._last_time = now
            return mbps
        except Exception:
            return None
