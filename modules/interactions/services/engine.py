from __future__ import annotations

from datetime import datetime
import logging
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

logger = logging.getLogger("interactions.engine")


class InteractionEngine:
    def __init__(
        self,
        cfg: Dict[str, Any],
        neo_client: Any | None = None,
        social_db: Any | None = None,
        expression_arbiter: Any | None = None,
    ):
        self.cfg = cfg
        self._expression_arbiter = expression_arbiter
        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self.metrics = MetricsCollector(window_s=int(cfg.get("thresholds", {}).get("cpu_load", {}).get("window_s", 60)))
        # If a local neo_client (NeoRunner) is provided, wrap it to match NeoHttpClient interface
        provided = neo_client
        if provided is not None:
            class _LocalNeoAdapter:
                def __init__(self, runner, engine_ref):
                    self._runner = runner
                    self._engine = engine_ref

                def clear(self) -> None:
                    try:
                        self._runner.clear()
                    except Exception:
                        pass

                def fill(self, r: int, g: int, b: int) -> None:
                    try:
                        self._runner.fill(r, g, b)
                    except Exception:
                        pass

                def animate(
                    self,
                    name: str,
                    emotions: Optional[list[str]] = None,
                    iterations: Optional[int] = None,
                    color: Optional[str | tuple[int, int, int]] = None,
                ) -> None:
                    try:
                        rgb = self._engine._normalize_color(color)
                        kwargs: Dict[str, Any] = {}
                        if rgb is not None:
                            kwargs["color"] = rgb
                        if emotions:
                            kwargs["emotions"] = emotions
                        if iterations is not None:
                            kwargs["iterations"] = iterations
                        self._runner.animate(name, **kwargs)
                    except Exception:
                        pass

                def set_base(self, name: str, color: Optional[str | tuple[int, int, int]] = None, speed: Optional[str] = None) -> None:
                    try:
                        rgb = self._engine._normalize_color(color)
                        if rgb is not None:
                            self._runner.animate(name, color=rgb)
                        else:
                            self._runner.animate(name)
                    except Exception:
                        pass

                def play_effect(
                    self,
                    name: str,
                    duration_ms: int = 800,
                    color: Optional[str | tuple[int, int, int]] = None,
                    emotions: Optional[list[str]] = None,
                ) -> None:
                    try:
                        rgb = self._engine._normalize_color(color)
                        kwargs: Dict[str, Any] = {}
                        if rgb is not None:
                            kwargs["color"] = rgb
                        if emotions:
                            kwargs["emotions"] = emotions
                        self._runner.animate(name, **kwargs)
                        import threading
                        import time

                        def _restore_idle():
                            try:
                                time.sleep(max(0.0, duration_ms / 1000.0))
                                idle = (self._engine.defaults or {}).get("idle", {}).get("base", {})
                                base_name = str(idle.get("name", "BREATHE"))
                                base_color = idle.get("color")
                                self._engine.neo.set_base(name=base_name, color=base_color)
                            except Exception:
                                pass

                        threading.Thread(target=_restore_idle, daemon=True).start()
                    except Exception:
                        pass

                def companion_mode(self, mode: str, eye_color: Any = None) -> None:
                    try:
                        if eye_color is not None:
                            rgb = self._engine._normalize_color(eye_color)
                            if rgb is not None and hasattr(self._runner, "companion_set_eye_color"):
                                self._runner.companion_set_eye_color(*rgb)
                        if hasattr(self._runner, "companion_set_mode"):
                            self._runner.companion_set_mode(str(mode))
                    except Exception:
                        pass

                def companion_vu(self, level: float, right: Optional[float] = None) -> None:
                    try:
                        if hasattr(self._runner, "companion_set_vu_level"):
                            self._runner.companion_set_vu_level(float(level), right=right)
                    except Exception:
                        pass

                def companion_is_active(self) -> bool:
                    try:
                        if hasattr(self._runner, "companion_is_active"):
                            return bool(self._runner.companion_is_active())
                    except Exception:
                        pass
                    return False

            self.neo = _LocalNeoAdapter(provided, self)
        else:
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
        self._event_counts: Dict[str, int] = {}
        self._last_net_burst: float = 0.0
        self.monitor_cfg = dict(cfg.get("monitor", {}))
        self._last_arduino_check = 0.0
        self._event_handlers: List[Any] = []
        self._manual_effect: Optional[Dict[str, Any]] = None
        self.quiet_hours_cfg = dict(cfg.get("quiet_hours", {}))

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
        evt = str(type_ or "").strip()
        with self._lock:
            self._ctx["event"] = evt
            if data:
                self._ctx.setdefault("event_data", {}).update(data)
            if evt:
                self._event_counts[evt] = int(self._event_counts.get(evt, 0)) + 1
        if evt.startswith("companion."):
            logger.info("Companion event received: %s data=%s", evt, data or {})
        if evt and self._social_db is not None:
            try:
                self._social_db.interaction_events.log(evt, payload=data or {})
            except Exception:
                pass
        for handler in list(self._event_handlers):
            try:
                handler(evt, data or {})
            except Exception:
                pass
        if evt == "speech.audio_level" and isinstance(data, dict):
            left = data.get("left")
            right = data.get("right")
            level = data.get("level")
            if hasattr(self.neo, "companion_vu"):
                try:
                    if left is not None and right is not None:
                        self.neo.companion_vu(float(left), right=float(right))
                    elif level is not None:
                        self.neo.companion_vu(float(level))
                except Exception:
                    pass

    def register_event_handler(self, handler) -> None:
        if handler is None:
            return
        self._event_handlers.append(handler)

    def set_state(self, **kwargs: Any) -> None:
        with self._lock:
            self._ctx.update(kwargs)

    @staticmethod
    def _normalize_color(color: Any) -> Optional[tuple[int, int, int]]:
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            try:
                return (int(color[0]) & 255, int(color[1]) & 255, int(color[2]) & 255)
            except (TypeError, ValueError):
                return None
        if isinstance(color, str):
            s = color.strip()
            if s.startswith("#") and len(s) >= 7:
                try:
                    v = int(s[1:7], 16)
                    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                except ValueError:
                    return None
        return None

    def trigger_effect(
        self,
        name: str,
        duration_ms: int = 800,
        force: bool = False,
        color: Any = None,
        emotions: Optional[list[str]] = None,
    ) -> None:
        if self._expression_arbiter is not None:
            try:
                if not self._expression_arbiter.claim_lights("interactions", force=bool(force)):
                    return
            except Exception:
                pass
        with self._lock:
            self._manual_effect = {
                "name": str(name),
                "duration_ms": int(duration_ms),
                "force": bool(force),
                "color": color,
                "emotions": emotions,
            }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "metrics": self._ctx.get("metrics"),
                "active_base": self._last_base,
                "effect_active": time.time() < self._active_effect_until,
                "event_counts": dict(self._event_counts),
                "ctx": {k: v for k, v in self._ctx.items() if k not in ("metrics",)},
            }

    # Loop
    def _loop(self) -> None:
        interval = float(self.cfg.get("tick_interval_ms", 800)) / 1000.0
        while not self._stop.is_set():
            self._tick()
            time.sleep(interval)

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

    def _evaluate_rules(self) -> Optional[Rule]:
        chosen: Optional[Rule] = None
        for r in self.rules:
            if eval_condition(r.when, dict(self._ctx)) and r.ready():
                if chosen is None or priority_rank(r.priority) > priority_rank(chosen.priority):
                    chosen = r
        return chosen

    def _render_manual_effect(self, now: float, manual_effect: dict) -> bool:
        if now < self._active_effect_until:
            return True
        if not (bool(manual_effect.get("force")) or self._effect_allowed("manual.effect")):
            return True
        name = str(manual_effect.get("name", "COMET"))
        duration_ms = int(manual_effect.get("duration_ms", 800))
        self._active_effect_until = now + duration_ms / 1000.0
        threading.Thread(
            target=self.neo.play_effect, args=(name, duration_ms),
            kwargs={"color": manual_effect.get("color"), "emotions": manual_effect.get("emotions")},
            daemon=True,
        ).start()
        return True

    def _render_manual_base(self, now: float, manual_base: tuple) -> bool:
        if now < self._active_effect_until:
            return True
        name, color = manual_base
        key = (str(name).upper(), color)
        if key != self._last_base:
            self._last_base = key
            self.neo.set_base(name=str(name), color=color)
        return True

    def _render_rule_companion(self, act: dict, chosen: Rule) -> bool:
        comp = act.get("companion")
        if not isinstance(comp, dict):
            return False
        mode = str(comp.get("mode", "off"))
        eye = comp.get("eye_color")
        if hasattr(self.neo, "companion_mode"):
            self.neo.companion_mode(mode, eye_color=eye)
        chosen.stamp()
        return True

    def _render_rule_effect(self, now: float, act: dict, chosen: Rule) -> bool:
        if "effect" not in act or now < self._active_effect_until:
            return False
        eff = act.get("effect") or {}
        name = str(eff.get("name", "COMET"))
        duration_ms = int(eff.get("duration_ms", 800))
        event_name = self._ctx.get("event")
        if not (self._effect_allowed(event_name) and self._claim_lights_for_event(event_name)):
            return True
        self._active_effect_until = now + duration_ms / 1000.0
        chosen.stamp()
        threading.Thread(
            target=self.neo.play_effect, args=(name, duration_ms),
            kwargs={"color": eff.get("color"), "emotions": eff.get("emotions") if isinstance(eff.get("emotions"), list) else None},
            daemon=True,
        ).start()
        return True

    def _render_rule_base(self, now: float, act: dict, chosen: Rule) -> bool:
        if "base" not in act or now < self._active_effect_until:
            return False
        base = act["base"] or {}
        name = str(base.get("name", self.defaults.get("idle", {}).get("base", {}).get("name", "BREATHE")))
        color = base.get("color")
        key = (name.upper(), color)
        if key != self._last_base:
            self._last_base = key
            self.neo.set_base(name=name, color=color)
            chosen.stamp()
        return True

    def _companion_controls_leds(self) -> bool:
        try:
            if hasattr(self.neo, "companion_is_active"):
                return bool(self.neo.companion_is_active())
        except Exception:
            pass
        return False

    def _render_idle_base(self, now: float) -> None:
        if now < self._active_effect_until:
            return
        if hasattr(self.neo, "companion_is_active") and self.neo.companion_is_active():
            return
        idle = self.defaults.get("idle", {}).get("base", {})
        name = str(idle.get("name", "BREATHE"))
        color = idle.get("color")
        key = (name.upper(), color)
        if key != self._last_base:
            self._last_base = key
            self.neo.set_base(name=name, color=color)

    def _tick(self) -> None:
        now = time.time()
        quiet_hours_active = self._is_quiet_hours_active()
        metrics = self.metrics.sample()
        self._update_arduino_state(now)
        net_burst = self._detect_net_burst(now, metrics)

        with self._lock:
            self._ctx["metrics"] = {
                "cpu_temp": metrics.cpu_temp, "cpu_load": metrics.cpu_load, "net_mbps": metrics.net_mbps,
            }
            self._ctx["arduino_connected"] = self._ctx.get("arduino_connected", True)
            self._ctx["net_burst"] = net_burst
            self._ctx["quiet_hours_active"] = quiet_hours_active

            manual_base = self._ctx.pop("manual_base", None)
            manual_effect = self._manual_effect
            self._manual_effect = None
            chosen = self._evaluate_rules()
            companion_leds = self._companion_controls_leds()

            rendered = False
            if manual_effect and now >= self._active_effect_until and not companion_leds:
                rendered = self._render_manual_effect(now, manual_effect)
            elif manual_base and now >= self._active_effect_until and not companion_leds:
                rendered = self._render_manual_base(now, manual_base)
            elif chosen:
                act = chosen.action or {}
                if "companion" in act:
                    rendered = self._render_rule_companion(act, chosen)
                elif not companion_leds:
                    rendered = self._render_rule_effect(now, act, chosen) or self._render_rule_base(now, act, chosen)

            if not rendered and not companion_leds:
                self._render_idle_base(now)

            self._ctx.pop("event", None)

    def _claim_lights_for_event(self, event_name: Any, *, force: bool = False) -> bool:
        if self._expression_arbiter is None:
            return True
        try:
            source = str(event_name or "interactions.rule")
            return bool(self._expression_arbiter.claim_lights(source, force=force))
        except Exception:
            return True

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
