from __future__ import annotations

from datetime import datetime
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:
    requests = None

logger = logging.getLogger("interactions.engine_guards")


class EngineGuardsMixin:
    """Quiet hours, network burst detection, lights claim arbiter, and Arduino monitoring."""

    cfg: Dict[str, Any]
    quiet_hours_cfg: Dict[str, Any]
    monitor_cfg: Dict[str, Any]
    _expression_arbiter: Any
    _lock: Any
    _lights_claim_generation: int
    _last_arduino_check: float
    _last_net_burst: float

    def set_state(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def _claim_lights_for_event(self, event_name: Any, *, force: bool = False) -> bool:
        if self._expression_arbiter is None:
            return True
        try:
            ok = bool(self._expression_arbiter.claim_lights("interactions", force=force))
            if ok:
                with self._lock:
                    self._lights_claim_generation += 1
            return ok
        except Exception:
            return True

    def _schedule_lights_release(self, duration_ms: int) -> None:
        if self._expression_arbiter is None:
            return
        with self._lock:
            generation = self._lights_claim_generation

        def _release() -> None:
            time.sleep(max(0.0, duration_ms / 1000.0))
            with self._lock:
                if generation != self._lights_claim_generation:
                    return
            try:
                self._expression_arbiter.release("interactions")
            except Exception:
                pass

        threading.Thread(target=_release, name="InteractionsLightsRelease", daemon=True).start()

    def _effect_allowed(self, event_name: Any) -> bool:
        if not bool(self.quiet_hours_cfg.get("enabled", False)):
            return True
        if not self._is_quiet_hours_active():
            return True
        if not bool(self.quiet_hours_cfg.get("suppress_effects", True)):
            return True
        allowed = self.quiet_hours_cfg.get("allow_events", []) or []
        if not isinstance(allowed, list):
            return False
        return str(event_name or "").strip() in {str(v).strip() for v in allowed}

    @staticmethod
    def _parse_hhmm(value: str) -> Optional[Tuple[int, int]]:
        text = str(value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            hh = int(parts[0])
            mm = int(parts[1])
        except Exception:
            return None
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return None
        return hh, mm

    def _is_quiet_hours_active(self) -> bool:
        if not bool(self.quiet_hours_cfg.get("enabled", False)):
            return False
        start = self._parse_hhmm(str(self.quiet_hours_cfg.get("start", "23:00")))
        end = self._parse_hhmm(str(self.quiet_hours_cfg.get("end", "07:00")))
        if start is None or end is None:
            return False
        now = datetime.now().hour * 60 + datetime.now().minute
        start_min = start[0] * 60 + start[1]
        end_min = end[0] * 60 + end[1]
        if start_min == end_min:
            return True
        if start_min < end_min:
            return start_min <= now < end_min
        return now >= start_min or now < end_min

    def _detect_net_burst(self, now: float, metrics) -> bool:
        try:
            thr = self.cfg.get("thresholds", {}).get("net", {})
            burst_mbps = float(thr.get("burst_mbps", 20))
            min_dur_ms = int(thr.get("min_duration_ms", 200))
            if metrics.net_mbps and metrics.net_mbps >= burst_mbps:
                self._last_net_burst = now + max(0.05, min_dur_ms / 1000.0)
                return True
            return now < self._last_net_burst
        except Exception:
            return False

    def _update_arduino_state(self, now: float) -> None:
        if requests is None:
            return
        cfg = self.monitor_cfg.get("arduino") if isinstance(self.monitor_cfg.get("arduino"), dict) else None
        if not cfg:
            return
        interval = float(cfg.get("interval_s", 5.0))
        if now - self._last_arduino_check < interval:
            return
        self._last_arduino_check = now
        url = str(cfg.get("url"))
        if not url:
            return
        timeout = float(cfg.get("timeout_s", 0.5))
        ok = False
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                ok = bool(data.get("ok", True))
        except Exception:
            ok = False
        self.set_state(arduino_connected=ok)
