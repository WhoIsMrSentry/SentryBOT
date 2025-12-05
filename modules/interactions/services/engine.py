from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from .metrics import MetricsCollector
from .rules import Rule, eval_condition, priority_rank
from .adapters.neopixel_client import NeoHttpClient, NoOpNeoClient


class InteractionEngine:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.metrics = MetricsCollector(window_s=int(cfg.get("thresholds", {}).get("cpu_load", {}).get("window_s", 60)))
        base_url = str(cfg.get("adapter", {}).get("http_base_url", "http://localhost:8092/neopixel"))
        self.neo = NeoHttpClient(base_url) if base_url else NoOpNeoClient()
        # rules
        self.rules: List[Rule] = []
        for r in cfg.get("rules", []) or []:
            self.rules.append(Rule(
                id=str(r.get("id")),
                priority=str(r.get("priority", "medium")),
                when=dict(r.get("when", {})),
                action=dict(r.get("action", {})),
                cooldown_ms=int(r.get("cooldown_ms", 0)),
            ))
        self.defaults = dict(cfg.get("defaults", {}))

        # runtime
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_base: Optional[Tuple[str, Optional[str | tuple[int, int, int]]]] = None
        self._active_effect_until: float = 0.0
        self._ctx: Dict[str, Any] = {"arduino_connected": False}
        self._last_net_burst: float = 0.0
        self.monitor_cfg = dict(cfg.get("monitor", {}))
        self._last_arduino_check = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="InteractionsEngine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    # API
    def push_event(self, type_: str, data: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._ctx["event"] = type_
            if data:
                self._ctx.setdefault("event_data", {}).update(data)

    def set_state(self, **kwargs: Any) -> None:
        with self._lock:
            self._ctx.update(kwargs)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "metrics": self._ctx.get("metrics"),
                "active_base": self._last_base,
                "effect_active": time.time() < self._active_effect_until,
                "ctx": {k: v for k, v in self._ctx.items() if k not in ("metrics",)},
            }

    # Loop
    def _loop(self) -> None:
        interval = float(self.cfg.get("tick_interval_ms", 800)) / 1000.0
        while not self._stop.is_set():
            self._tick()
            time.sleep(interval)

    def _tick(self) -> None:
        now = time.time()
        metrics = self.metrics.sample()
        self._update_arduino_state(now)
        net_burst = False
        try:
            thr = self.cfg.get("thresholds", {}).get("net", {})
            burst_mbps = float(thr.get("burst_mbps", 20))
            min_dur_ms = int(thr.get("min_duration_ms", 200))
            if metrics.net_mbps and metrics.net_mbps >= burst_mbps:
                net_burst = True
                self._last_net_burst = now + max(0.05, min_dur_ms / 1000.0)
            elif now < self._last_net_burst:
                net_burst = True
        except Exception:
            pass

        with self._lock:
            self._ctx["metrics"] = {
                "cpu_temp": metrics.cpu_temp,
                "cpu_load": metrics.cpu_load,
                "net_mbps": metrics.net_mbps,
            }
            self._ctx["arduino_connected"] = self._ctx.get("arduino_connected", True)
            self._ctx["net_burst"] = net_burst

            # Evaluate rules
            manual_base = self._ctx.pop("manual_base", None)
            chosen: Optional[Rule] = None
            for r in self.rules:
                ctx = dict(self._ctx)
                if eval_condition(r.when, ctx) and r.ready():
                    if chosen is None or priority_rank(r.priority) > priority_rank(chosen.priority):
                        chosen = r

            # Render
            if manual_base and now >= self._active_effect_until:
                name, color = manual_base
                key = (str(name).upper(), color)
                if key != self._last_base:
                    self._last_base = key
                    self.neo.set_base(name=str(name), color=color)
            elif chosen:
                act = chosen.action or {}
                # effect or base
                if "effect" in act and now >= self._active_effect_until:
                    eff = act["effect"] or {}
                    name = str(eff.get("name", "COMET"))
                    duration_ms = int(eff.get("duration_ms", 800))
                    self._active_effect_until = now + duration_ms / 1000.0
                    chosen.stamp()
                    # play effect asynchronously to avoid blocking
                    threading.Thread(target=self.neo.play_effect, args=(name, duration_ms), daemon=True).start()
                elif "base" in act and now >= self._active_effect_until:
                    base = act["base"] or {}
                    name = str(base.get("name", self.defaults.get("idle", {}).get("base", {}).get("name", "BREATHE")))
                    color = base.get("color")
                    # Apply only if changed
                    key = (name.upper(), color)
                    if key != self._last_base:
                        self._last_base = key
                        self.neo.set_base(name=name, color=color)
                        chosen.stamp()
            else:
                # No rule matched; ensure idle base
                if now >= self._active_effect_until:
                    idle = self.defaults.get("idle", {}).get("base", {})
                    name = str(idle.get("name", "BREATHE"))
                    color = idle.get("color")
                    key = (name.upper(), color)
                    if key != self._last_base:
                        self._last_base = key
                        self.neo.set_base(name=name, color=color)

            # one-shot event is consumed
            self._ctx.pop("event", None)

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
