from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .rules import Rule, eval_condition, priority_rank

logger = logging.getLogger("interactions.engine_render")


class EngineRenderMixin:
    """LED effects rendering, dispatching, and companion rule translation."""

    neo: Any
    defaults: Dict[str, Any]
    rules: List[Rule]
    brightness: float
    _lock: threading.RLock
    _restore_timer_lock: threading.Lock
    _restore_timer: Optional[threading.Timer]
    _stop: threading.Event
    _last_base: Optional[Tuple[Any, ...]]
    _active_effect_until: float
    _effect_gen: int
    _ctx: Dict[str, Any]
    _event_handlers: List[Any]
    _via_expression: bool

    if TYPE_CHECKING:
        def _effect_allowed(self, event_name: Any) -> bool: ...
        def _claim_lights_for_event(
            self,
            event_name: Any,
            *,
            force: bool = False,
            ttl_ms: Optional[int] = None,
        ) -> bool: ...
        def _schedule_lights_release(self, duration_ms: int) -> None: ...
        @staticmethod
        def _normalize_color(color: Any) -> Optional[tuple[int, int, int]]: ...

    def _uses_expression_output(self) -> bool:
        return bool(self._via_expression and self._event_handlers)

    def _scale_color(self, color: Any) -> Any:
        if color is None or getattr(self, "brightness", 1.0) >= 0.999:
            return color
        rgb = self._normalize_color(color)
        if rgb is None:
            return color
        b = max(0.05, min(1.0, float(self.brightness)))
        return (int(round(rgb[0] * b)), int(round(rgb[1] * b)), int(round(rgb[2] * b)))

    def _notify_expression(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = dict(data or {})
        payload.setdefault("brightness", float(getattr(self, "brightness", 1.0)))
        for handler in list(self._event_handlers):
            try:
                handler(event_type, payload)
            except Exception:
                logger.debug("expression handler failed for %s", event_type, exc_info=True)

    def _schedule_effect_restore(self, duration_ms: int, generation: int) -> None:
        with self._restore_timer_lock:
            if self._restore_timer is not None:
                try:
                    self._restore_timer.cancel()
                except Exception:
                    pass
                self._restore_timer = None

        def _restore() -> None:
            if self._stop.is_set() or self._companion_controls_leds():
                return
            with self._lock:
                if generation != self._effect_gen:
                    return
                if time.time() < self._active_effect_until - 0.005:
                    return
                idle = self.defaults.get("idle", {}).get("base", {})
                base_name = str(idle.get("name", "BREATHE"))
                base_color = self._scale_color(idle.get("color"))
                key = (base_name.upper(), base_color)
                self._last_base = key
            self.neo.set_base(name=base_name, color=base_color)

        delay_s = max(0.01, float(duration_ms) / 1000.0)
        timer = threading.Timer(delay_s, _restore)
        timer.name = "InteractionsEffectRestore"
        timer.daemon = True
        with self._restore_timer_lock:
            self._restore_timer = timer
        timer.start()

    def _start_effect_worker(
        self,
        name: str,
        duration_ms: int,
        *,
        color: Any,
        emotions: Any,
        generation: int,
    ) -> None:
        def _run() -> None:
            try:
                self.neo.play_effect(name, duration_ms, color=color, emotions=emotions)
            except Exception as exc:
                logger.debug("neo.play_effect failed for '%s': %s", name, exc)

        threading.Thread(target=_run, name="InteractionsPlayEffect", daemon=True).start()
        self._schedule_lights_release(duration_ms)
        self._schedule_effect_restore(duration_ms, generation)

    def _render_manual_effect(self, now: float, manual_effect: dict) -> bool:
        force = bool(manual_effect.get("force", False))
        with self._lock:
            if not force and now < self._active_effect_until:
                return True
        if not (force or self._effect_allowed("manual.effect")):
            self._schedule_lights_release(0)
            return True
        name = str(manual_effect.get("name", "COMET"))
        duration_ms = max(0, int(manual_effect.get("duration_ms", 800)))
        color = manual_effect.get("color")
        emotions = manual_effect.get("emotions")
        with self._lock:
            self._active_effect_until = now + duration_ms / 1000.0
            self._effect_gen += 1
            self._last_base = None
            generation = self._effect_gen
        self._start_effect_worker(
            name,
            duration_ms,
            color=color,
            emotions=emotions,
            generation=generation,
        )
        return True

    def _render_manual_base(self, now: float, manual_base: tuple) -> bool:
        name, color = manual_base
        key = (str(name).upper(), color)
        should_send = False
        with self._lock:
            if now < self._active_effect_until:
                return True
            if key != self._last_base:
                self._last_base = key
                should_send = True
        if should_send:
            self.neo.set_base(name=str(name), color=color)
        return True

    def _render_rule_companion(self, act: dict, chosen: Rule) -> bool:
        comp = act.get("companion")
        if not isinstance(comp, dict):
            return False
        mode = str(comp.get("mode", "off"))
        eye = comp.get("eye_color")
        with self._lock:
            self._last_base = None
            chosen.stamp()
        if hasattr(self.neo, "companion_mode"):
            self.neo.companion_mode(mode, eye_color=eye)
        return True

    def _dispatch_rule_for_event(self, evt: str) -> bool:
        if not evt:
            return False
        with self._lock:
            snapshot = dict(self._ctx)
            snapshot["event"] = evt
            chosen: Optional[Rule] = None
            for rule in self.rules:
                if "event" not in rule.when:
                    continue
                if not eval_condition(rule.when, snapshot):
                    continue
                rule.mark_matched()
                if not rule.ready():
                    continue
                if chosen is None or priority_rank(rule.priority) > priority_rank(chosen.priority):
                    chosen = rule
            if chosen is None:
                return False
            act = chosen.action or {}
            if self._uses_expression_output():
                if "effect" in act:
                    eff = act.get("effect") or {}
                    dur = max(0, int(eff.get("duration_ms", 800)))
                    chosen_stamp_only = False
                else:
                    dur = 0
                    chosen_stamp_only = True
                if chosen_stamp_only:
                    chosen.stamp()
                    return True
        if self._uses_expression_output():
            eff = act.get("effect") or {}
            dur = max(0, int(eff.get("duration_ms", 800)))
            if not (self._effect_allowed(evt) and self._claim_lights_for_event(evt, ttl_ms=dur)):
                return True
            with self._lock:
                self._active_effect_until = time.time() + dur / 1000.0
                self._effect_gen += 1
                self._last_base = None
                chosen.stamp()
            self._schedule_lights_release(dur)
            return True
        if "companion" in act:
            return self._render_rule_companion(act, chosen)
        now = time.time()
        return self._render_rule_effect(now, act, chosen, event_name=evt) or self._render_rule_base(now, act, chosen)

    def _render_rule_effect(
        self,
        now: float,
        act: dict,
        chosen: Rule,
        event_name: Any = None,
    ) -> bool:
        if "effect" not in act:
            return False
        with self._lock:
            if now < self._active_effect_until:
                return False
            ev_name = event_name or self._ctx.get("event")
        eff = act.get("effect") or {}
        name = str(eff.get("name", "COMET"))
        duration_ms = max(0, int(eff.get("duration_ms", 800)))
        if not (self._effect_allowed(ev_name) and self._claim_lights_for_event(ev_name, ttl_ms=duration_ms)):
            return True
        color = self._scale_color(eff.get("color"))
        emotions = eff.get("emotions") if isinstance(eff.get("emotions"), list) else None
        with self._lock:
            self._active_effect_until = now + duration_ms / 1000.0
            self._effect_gen += 1
            self._last_base = None
            generation = self._effect_gen
            chosen.stamp()
        self._start_effect_worker(
            name,
            duration_ms,
            color=color,
            emotions=emotions,
            generation=generation,
        )
        return True

    def _render_rule_base(self, now: float, act: dict, chosen: Rule) -> bool:
        if "base" not in act:
            return False
        base = act["base"] or {}
        name = str(base.get("name", self.defaults.get("idle", {}).get("base", {}).get("name", "BREATHE")))
        color = self._scale_color(base.get("color"))
        key = (name.upper(), color)
        should_send = False
        with self._lock:
            if now < self._active_effect_until:
                return False
            if key != self._last_base:
                self._last_base = key
                chosen.stamp()
                should_send = True
        if should_send:
            self.neo.set_base(name=name, color=color)
        return True

    def _companion_controls_leds(self) -> bool:
        try:
            if hasattr(self.neo, "companion_is_active"):
                return bool(self.neo.companion_is_active())
        except Exception:
            pass
        return False

    def _render_idle_base(self, now: float) -> None:
        if self._companion_controls_leds():
            return
        idle = self.defaults.get("idle", {}).get("base", {})
        name = str(idle.get("name", "BREATHE"))
        color = self._scale_color(idle.get("color"))
        key = (name.upper(), color)
        should_send = False
        with self._lock:
            if now < self._active_effect_until:
                return
            if key != self._last_base:
                self._last_base = key
                should_send = True
        if should_send:
            self.neo.set_base(name=name, color=color)

    def _emit_idle_expression(self) -> None:
        key = ("expression.idle", None)
        with self._lock:
            if time.time() < self._active_effect_until or key == self._last_base:
                return
            self._last_base = key
        self._notify_expression("interactions.idle", {"rule": "idle"})
