from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


@dataclass
class SysMetrics:
    cpu_temp: Optional[float] = None
    cpu_load: Optional[float] = None  # 0..1
    net_mbps: Optional[float] = None
    arduino_connected: Optional[bool] = None


class MetricsCollector:
    def __init__(self, window_s: int = 60) -> None:
        self.window_s = window_s
        self._last_net = None
        self._last_time = None

    def sample(self) -> SysMetrics:
        m = SysMetrics()
        # CPU temperature
        m.cpu_temp = self._read_cpu_temp()
        # load
        m.cpu_load = self._read_cpu_load()
        # network
        m.net_mbps = self._read_net_speed_mbps()
        # arduino (placeholder): external health check can set this via event/state
        return m

    def _read_cpu_temp(self) -> Optional[float]:
        if psutil is None:
            return None
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None
            # pick first available
            for _, arr in temps.items():
                if arr:
                    return float(getattr(arr[0], "current", None) or getattr(arr[0], "temp", None))
        except Exception:
            pass
        # Fallback for Linux thermal zone
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
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
            now = time.time()
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
