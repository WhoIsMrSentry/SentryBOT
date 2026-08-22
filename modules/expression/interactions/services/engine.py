from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .metrics import MetricsCollector
from .rules import Rule, eval_condition, priority_rank
from .adapters.neopixel_client import NeoHttpClient, NoOpNeoClient
from .engine_guards import EngineGuardsMixin
from .engine_render import EngineRenderMixin

logger = logging.getLogger("interactions.engine")


class InteractionEngine(EngineGuardsMixin, EngineRenderMixin):
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
                from modules.cognitive_memory import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self.metrics = MetricsCollector(window_s=int(cfg.get("thresholds", {}).get("cpu_load", {}).get("window_s", 60)))
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
                        if hasattr(self._runner, "companion_is_active") and self._runner.companion_is_active():
                            return
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
                        if hasattr(self._runner, "companion_is_active") and self._runner.companion_is_active():
                            return
                        rgb = self._engine._normalize_color(color)
                        kwargs: Dict[str, Any] = {}
                        if rgb is not None:
                            kwargs["color"] = rgb
                        if emotions:
                            kwargs["emotions"] = emotions
                        self._runner.animate(name, **kwargs)

                        def _restore_idle():
                            try:
                                time.sleep(max(0.0, duration_ms / 1000.0))
                                if hasattr(self._runner, "companion_is_active") and self._runner.companion_is_active():
                                    return
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

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._event_dispatch_lock = threading.Lock()
        self._last_base: Optional[Tuple[str, Optional[str | tuple[int, int, int]]]] = None
        self._active_effect_until: float = 0.0
        self._ctx: Dict[str, Any] = {"arduino_connected": True}
        self._event_counts: Dict[str, int] = {}
        self._last_net_burst: float = 0.0
        self.monitor_cfg = dict(cfg.get("monitor", {}))
        self._last_arduino_check = 0.0
        self._event_handlers: List[Any] = []
        self._manual_effect: Optional[Dict[str, Any]] = None
        self._last_event = ""
        self._last_event_data: Dict[str, Any] = {}
        self._lights_claim_generation = 0
        self.quiet_hours_cfg = dict(cfg.get("quiet_hours", {}))
        output_cfg = cfg.get("output") if isinstance(cfg.get("output"), dict) else {}
        self._via_expression = bool(output_cfg.get("via_expression", True))

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

    def push_event(self, type_: str, data: Optional[Dict[str, Any]] = None) -> None:
        evt = str(type_ or "").strip()
        event_data = dict(data or {})
        with self._lock:
            if evt:
                self._event_counts[evt] = int(self._event_counts.get(evt, 0)) + 1
                self._last_event = evt
                self._last_event_data = event_data
        if evt.startswith("companion."):
            logger.info("Companion event received: %s data=%s", evt, data or {})
        if evt and self._social_db is not None:
            try:
                self._social_db.interaction_events.log(evt, payload=data or {})
            except Exception:
                pass
        for handler in list(self._event_handlers):
            try:
                handler(evt, event_data)
            except Exception:
                pass
        with self._event_dispatch_lock:
            self._dispatch_rule_for_event(evt)

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
        if not self._claim_lights_for_event("manual.effect", force=bool(force)):
            return
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
                "last_event": self._last_event,
                "last_event_data": dict(self._last_event_data),
                "ctx": {k: v for k, v in self._ctx.items() if k not in ("metrics",)},
            }

    def _loop(self) -> None:
        interval = float(self.cfg.get("tick_interval_ms", 800)) / 1000.0
        while not self._stop.is_set():
            self._tick()
            time.sleep(interval)

    def _evaluate_rules(self) -> Optional[Rule]:
        chosen: Optional[Rule] = None
        for r in self.rules:
            if eval_condition(r.when, dict(self._ctx)) and r.ready():
                if chosen is None or priority_rank(r.priority) > priority_rank(chosen.priority):
                    chosen = r
        return chosen

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
            if manual_effect and companion_leds:
                self._schedule_lights_release(0)
                rendered = True
            elif manual_effect and now >= self._active_effect_until:
                if self._uses_expression_output():
                    self._notify_expression("interactions.effect", dict(manual_effect))
                    rendered = True
                else:
                    rendered = self._render_manual_effect(now, manual_effect)
            elif manual_base and now >= self._active_effect_until and not companion_leds:
                if self._uses_expression_output():
                    self._notify_expression("interactions.base", {"name": manual_base[0], "color": manual_base[1]})
                    rendered = True
                else:
                    rendered = self._render_manual_base(now, manual_base)
            elif chosen:
                act = chosen.action or {}
                if self._uses_expression_output():
                    self._notify_expression(f"interactions.{chosen.id}", {"rule": chosen.id, "action": act})
                    chosen.stamp()
                    rendered = True
                elif "companion" in act:
                    rendered = self._render_rule_companion(act, chosen)
                elif not companion_leds:
                    rendered = self._render_rule_effect(now, act, chosen) or self._render_rule_base(now, act, chosen)

            if not rendered and not companion_leds:
                if self._uses_expression_output():
                    self._emit_idle_expression()
                else:
                    self._render_idle_base(now)
