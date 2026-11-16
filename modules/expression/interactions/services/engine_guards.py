from __future__ import annotations

from datetime import datetime
import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

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
    _lock: threading.RLock
    _restore_timer_lock: threading.Lock
    _release_timer: Optional[threading.Timer]
    _lights_claim_generation: int
    _last_arduino_check: float
    _last_net_burst: float
    _arduino_fail_logged: bool

    if TYPE_CHECKING:
        def set_state(self, **kwargs: Any) -> None: ...

    def _claim_lights_for_event(
        self,
        event_name: Any,
        *,
        force: bool = False,
        ttl_ms: Optional[int] = None,
    ) -> bool:
        if self._expression_arbiter is None:
            return True
        semantic = str(event_name or "").strip()
        ttl_s = max(0.05, float(ttl_ms) / 1000.0) if ttl_ms and ttl_ms > 0 else None
        try:
            try:
                ok = bool(
                    self._expression_arbiter.claim_lights(
                        "interactions",
                        force=force,
                        ttl_s=ttl_s,
                        semantic=semantic,
                    )
                )
            except TypeError:
                ok = bool(self._expression_arbiter.claim_lights("interactions", force=force))
            if ok:
                with self._lock:
                    self._lights_claim_generation += 1
            return ok
        except Exception as exc:
            logger.warning("expression arbiter claim_lights failed (fail-closed) for '%s': %s", semantic, exc)
            return False

    def _cancel_release_timer(self) -> None:
        with self._restore_timer_lock:
            timer = getattr(self, "_release_timer", None)
            if timer is not None:
                try:
                    timer.cancel()
                except Exception:
                    pass
                self._release_timer = None

    def _release_lights_now(self) -> None:
        if self._expression_arbiter is None:
            return
        try:
            self._expression_arbiter.release("interactions")
        except Exception as exc:
            logger.debug("expression arbiter release failed: %s", exc)

    def _schedule_lights_release(self, duration_ms: int) -> None:
        if self._expression_arbiter is None:
            return
        self._cancel_release_timer()
        if duration_ms <= 0:
            self._release_lights_now()
            return
        with self._lock:
            generation = self._lights_claim_generation

        def _release() -> None:
            with self._lock:
                if generation != self._lights_claim_generation:
                    return
            self._release_lights_now()

        timer = threading.Timer(max(0.0, float(duration_ms) / 1000.0), _release)
        timer.name = "InteractionsLightsRelease"
        timer.daemon = True
        with self._restore_timer_lock:
            self._release_timer = timer
        timer.start()

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
        from modules.common.time_utils import parse_hhmm
        return parse_hhmm(value)

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

    def _detect_net_burst(self, now: float, metrics: Any) -> bool:
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

    @staticmethod
    def _resolve_monitor_url(raw_url: str) -> str:
        url = str(raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("@gateway"):
            try:
                from modules.gateway.url import resolve_config_url, resolve_gateway_base_url

                return resolve_config_url(url, resolve_gateway_base_url())
            except Exception as exc:
                logger.warning("Failed to resolve gateway URL '%s': %s", url, exc)
                return ""
        return url

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
        url = self._resolve_monitor_url(str(cfg.get("url") or ""))
        if not url:
            return
        timeout = float(cfg.get("timeout_s", 0.5))
        ok = False
        err_msg = ""
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                ok = bool(data.get("ok", True))
                if not ok:
                    err_msg = str(data.get("error") or "status ok=False")
            else:
                err_msg = f"HTTP {resp.status_code}"
        except Exception as exc:
            ok = False
            err_msg = str(exc)
        if not ok:
            if not getattr(self, "_arduino_fail_logged", False):
                logger.warning("Arduino health probe failed (%s): %s", url, err_msg)
                self._arduino_fail_logged = True
            else:
                logger.debug("Arduino health probe failed (%s): %s", url, err_msg)
        else:
            if getattr(self, "_arduino_fail_logged", False):
                logger.info("Arduino health probe recovered (%s)", url)
                self._arduino_fail_logged = False
        self.set_state(arduino_connected=ok)
