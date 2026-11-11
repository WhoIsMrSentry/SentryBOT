from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .metrics import MetricsCollector
from .rules import Rule, eval_condition, priority_rank, validate_rules_config
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
        self._restore_timer: Optional[threading.Timer] = None
        self._release_timer: Optional[threading.Timer] = None
        self._effect_gen: int = 0
        self._restore_timer_lock = threading.Lock()
        self._arduino_fail_logged: bool = False
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

                def set_base(
                    self,
                    name: str,
                    color: Optional[str | tuple[int, int, int]] = None,
                    speed: Optional[str] = None,
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
            # Engine coordinates idle base restoration under quiet_hours & arbiter guards
            self.neo = NeoHttpClient(base_url, idle_base=None) if base_url else NoOpNeoClient()

        raw_rules = cfg.get("rules", []) or []
        self.rule_warnings: List[str] = validate_rules_config(raw_rules)
        for warning_msg in self.rule_warnings:
            logger.warning("interactions config rule warning: %s", warning_msg)

        self.rules: List[Rule] = []
        for r in raw_rules:
            if not isinstance(r, dict):
                continue
            self.rules.append(Rule(
                id=str(r.get("id")),
                priority=str(r.get("priority", "medium")),
                when=dict(r.get("when", {})) if isinstance(r.get("when"), dict) else {},
                action=dict(r.get("action", {})) if isinstance(r.get("action"), dict) else {},
                cooldown_ms=int(r.get("cooldown_ms", 0)),
            ))
        self.defaults = dict(cfg.get("defaults", {}))
        try:
            self.brightness = max(0.05, min(1.0, float(self.defaults.get("brightness", 1.0))))
        except (TypeError, ValueError):
            self.brightness = 1.0

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._event_dispatch_lock = threading.Lock()
        self._last_base: Optional[Tuple[Any, ...]] = None
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
        with self._restore_timer_lock:
            for attr in ("_restore_timer", "_release_timer"):
                timer = getattr(self, attr, None)
                if timer is not None:
                    try:
                        timer.cancel()
                    except Exception:
                        pass
                    setattr(self, attr, None)
        self._release_lights_now()
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

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
        from modules.common.color_utils import normalize_color
        return normalize_color(color)

    def request_effect(
        self,
        name: str,
        duration_ms: int = 800,
        force: bool = False,
        color: Any = None,
        emotions: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        dur = max(0, int(duration_ms))
        if not force and self._companion_controls_leds():
            return {"ok": False, "reason": "companion_active"}
        if not force and not self._effect_allowed("manual.effect"):
            return {"ok": False, "reason": "quiet_hours"}
        if not self._claim_lights_for_event("manual.effect", force=bool(force), ttl_ms=dur):
            return {"ok": False, "reason": "arbiter_rejected"}
        with self._lock:
            self._manual_effect = {
                "name": str(name),
                "duration_ms": dur,
                "force": bool(force),
                "color": color,
                "emotions": list(emotions) if isinstance(emotions, list) else emotions,
            }
            if force:
                self._active_effect_until = 0.0
        return {"ok": True}

    def trigger_effect(
        self,
        name: str,
        duration_ms: int = 800,
        force: bool = False,
        color: Any = None,
        emotions: Optional[list[str]] = None,
    ) -> bool:
        return bool(
            self.request_effect(
                name=name,
                duration_ms=duration_ms,
                force=force,
                color=color,
                emotions=emotions,
            ).get("ok")
        )

    def request_base(
        self,
        name: str,
        color: Any = None,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not force and self._companion_controls_leds():
            return {"ok": False, "reason": "companion_active"}
        if not force and not self._effect_allowed("manual.base"):
            return {"ok": False, "reason": "quiet_hours"}
        if not self._claim_lights_for_event("manual.base", force=bool(force)):
            return {"ok": False, "reason": "arbiter_rejected"}
        self.set_state(manual_base=(str(name), color))
        return {"ok": True}

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "metrics": self._ctx.get("metrics"),
                "active_base": self._last_base,
                "effect_active": time.time() < self._active_effect_until,
                "brightness": self.brightness,
                "event_counts": dict(self._event_counts),
                "last_event": self._last_event,
                "last_event_data": dict(self._last_event_data),
                "ctx": {k: v for k, v in self._ctx.items() if k not in ("metrics",)},
            }

    def get_rules_trace(self) -> Dict[str, Any]:
        now = time.time()
        now_mono = time.monotonic()
        quiet_enabled = bool(self.quiet_hours_cfg.get("enabled", False))
        quiet_active = self._is_quiet_hours_active()
        arbiter_info: Any = None
        if self._expression_arbiter is not None:
            try:
                if hasattr(self._expression_arbiter, "detailed_status"):
                    arbiter_info = self._expression_arbiter.detailed_status()
                elif hasattr(self._expression_arbiter, "status"):
                    arbiter_info = self._expression_arbiter.status()
            except Exception as exc:
                arbiter_info = {"error": str(exc)}
        with self._lock:
            effect_rem = round(max(0.0, self._active_effect_until - now), 3)
            rules_trace = [r.trace_snapshot(now_mono=now_mono) for r in self.rules]
            last_base = self._last_base
            lease_active = bool(effect_rem > 0)
            if isinstance(arbiter_info, dict):
                owners = arbiter_info.get("owners") if isinstance(arbiter_info.get("owners"), dict) else arbiter_info
                lease_active = owners.get("lights_owner") == "interactions"
        return {
            "ok": True,
            "via_expression": self._via_expression,
            "active_base": last_base,
            "quiet_hours": {
                "enabled": quiet_enabled,
                "active": quiet_active,
                "suppress_effects": bool(self.quiet_hours_cfg.get("suppress_effects", True)),
                "start": self.quiet_hours_cfg.get("start"),
                "end": self.quiet_hours_cfg.get("end"),
            },
            "lease": {
                "source": "interactions",
                "active": lease_active,
                "effect_active": effect_rem > 0,
                "effect_remaining_s": effect_rem,
                "arbiter": arbiter_info,
            },
            "config_warnings": list(self.rule_warnings),
            "rules": rules_trace,
        }

    def _loop(self) -> None:
        interval = max(0.01, float(self.cfg.get("tick_interval_ms", 800)) / 1000.0)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.warning("interactions tick failed: %s", exc)
            self._stop.wait(timeout=interval)

    def _evaluate_rules(self) -> tuple[Optional[Rule], bool]:
        """Evaluate non-event rules; return (chosen_ready_rule, holding_active_base)."""
        chosen: Optional[Rule] = None
        holding_base = False
        snapshot = dict(self._ctx)
        for r in self.rules:
            if not eval_condition(r.when, snapshot):
                continue
            r.mark_matched()
            act = r.action or {}
            if "base" in act and self._last_base is not None:
                base_cfg = act.get("base") or {}
                bkey_direct = (str(base_cfg.get("name", "BREATHE")).upper(), self._scale_color(base_cfg.get("color")))
                bkey_expr = (
                    "rule_base",
                    r.id,
                    str(base_cfg.get("name", "")).upper(),
                    self._scale_color(base_cfg.get("color")),
                )
                if self._last_base in (bkey_direct, bkey_expr):
                    holding_base = True
            if r.ready():
                if chosen is None or priority_rank(r.priority) > priority_rank(chosen.priority):
                    chosen = r
        return chosen, holding_base

    def _tick(self) -> None:
        now = time.time()
        quiet_hours_active = self._is_quiet_hours_active()
        metrics = self.metrics.sample()
        self._update_arduino_state(now)
        net_burst = self._detect_net_burst(now, metrics)
        companion_leds = self._companion_controls_leds()
        via_expr = self._uses_expression_output()

        decision: Optional[Tuple[str, Any]] = None

        with self._lock:
            self._ctx["metrics"] = {
                "cpu_temp": metrics.cpu_temp,
                "cpu_load": metrics.cpu_load,
                "net_mbps": metrics.net_mbps,
            }
            self._ctx["arduino_connected"] = self._ctx.get("arduino_connected", True)
            self._ctx["net_burst"] = net_burst
            self._ctx["quiet_hours_active"] = quiet_hours_active

            manual_base = self._ctx.pop("manual_base", None)
            manual_effect = None
            if self._manual_effect is not None:
                if self._manual_effect.get("force") or now >= self._active_effect_until:
                    manual_effect = self._manual_effect
                    self._manual_effect = None

            chosen_rule, holding_active_base = self._evaluate_rules()
            effect_active = now < self._active_effect_until

            if manual_effect and companion_leds:
                decision = ("companion_release", None)
            elif manual_effect and (manual_effect.get("force") or not effect_active):
                if via_expr:
                    dur = max(0, int(manual_effect.get("duration_ms", 800)))
                    self._active_effect_until = now + dur / 1000.0
                    self._effect_gen += 1
                    self._last_base = None
                    decision = ("expr_manual_effect", dict(manual_effect))
                else:
                    decision = ("direct_manual_effect", dict(manual_effect))
            elif manual_base and not effect_active and not companion_leds:
                if via_expr:
                    key = ("manual_base", str(manual_base[0]).upper(), manual_base[1])
                    if key != self._last_base:
                        self._last_base = key
                        decision = ("expr_manual_base", manual_base)
                    else:
                        decision = ("noop", None)
                else:
                    decision = ("direct_manual_base", manual_base)
            elif chosen_rule:
                act = chosen_rule.action or {}
                if via_expr:
                    if "effect" in act:
                        if not effect_active:
                            decision = ("expr_rule_effect", (chosen_rule, act))
                    elif "base" in act:
                        if not effect_active:
                            base_cfg = act.get("base") or {}
                            bkey = (
                                "rule_base",
                                chosen_rule.id,
                                str(base_cfg.get("name", "")).upper(),
                                self._scale_color(base_cfg.get("color")),
                            )
                            if bkey != self._last_base:
                                self._last_base = bkey
                                chosen_rule.stamp()
                                decision = ("expr_rule_notify", (chosen_rule, act))
                            else:
                                decision = ("noop", None)
                    elif "companion" in act:
                        self._last_base = None
                        chosen_rule.stamp()
                        decision = ("expr_rule_notify", (chosen_rule, act))
                elif "companion" in act:
                    decision = ("direct_rule_companion", (chosen_rule, act))
                elif not companion_leds and not effect_active:
                    if "effect" in act:
                        decision = ("direct_rule_effect", (chosen_rule, act))
                    elif "base" in act:
                        decision = ("direct_rule_base", (chosen_rule, act))

            if decision is None and not companion_leds and not effect_active:
                if holding_active_base:
                    decision = ("noop", None)
                else:
                    decision = ("expr_idle" if via_expr else "direct_idle", None)

        # Dispatch external notifications & hardware I/O strictly OUTSIDE self._lock
        if decision is None or decision[0] == "noop":
            return
        kind, payload = decision
        if kind == "companion_release":
            self._schedule_lights_release(0)
        elif kind == "expr_manual_effect":
            dur = max(0, int(payload.get("duration_ms", 800)))
            self._notify_expression("interactions.effect", payload)
            self._schedule_lights_release(dur)
        elif kind == "direct_manual_effect":
            self._render_manual_effect(now, payload)
        elif kind == "expr_manual_base":
            self._notify_expression("interactions.base", {"name": payload[0], "color": payload[1]})
        elif kind == "direct_manual_base":
            self._render_manual_base(now, payload)
        elif kind == "expr_rule_effect":
            rule_obj, act = payload
            eff = act.get("effect") or {}
            dur = max(0, int(eff.get("duration_ms", 800)))
            if self._effect_allowed(rule_obj.id) and self._claim_lights_for_event(rule_obj.id, ttl_ms=dur):
                with self._lock:
                    self._active_effect_until = time.time() + dur / 1000.0
                    self._effect_gen += 1
                    self._last_base = None
                    rule_obj.stamp()
                self._notify_expression(f"interactions.{rule_obj.id}", {"rule": rule_obj.id, "action": act})
                self._schedule_lights_release(dur)
        elif kind == "expr_rule_notify":
            rule_obj, act = payload
            self._notify_expression(f"interactions.{rule_obj.id}", {"rule": rule_obj.id, "action": act})
        elif kind == "direct_rule_companion":
            rule_obj, act = payload
            self._render_rule_companion(act, rule_obj)
        elif kind == "direct_rule_effect":
            rule_obj, act = payload
            self._render_rule_effect(now, act, rule_obj)
        elif kind == "direct_rule_base":
            rule_obj, act = payload
            self._render_rule_base(now, act, rule_obj)
        elif kind == "expr_idle":
            self._emit_idle_expression()
        elif kind == "direct_idle":
            self._render_idle_base(now)
