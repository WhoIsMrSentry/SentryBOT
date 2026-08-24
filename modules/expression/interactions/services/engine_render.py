from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .rules import Rule, eval_condition, priority_rank

logger = logging.getLogger("interactions.engine_render")


class EngineRenderMixin:
    """LED effects rendering, dispatching, and companion rule translation."""

    neo: Any
    defaults: Dict[str, Any]
    rules: List[Rule]
    _lock: Any
    _last_base: Optional[Tuple[str, Optional[str | tuple[int, int, int]]]]
    _active_effect_until: float
    _ctx: Dict[str, Any]
    _event_handlers: List[Any]
    _via_expression: bool

    def _effect_allowed(self, event_name: Any) -> bool:
        raise NotImplementedError

    def _claim_lights_for_event(self, event_name: Any, *, force: bool = False) -> bool:
        raise NotImplementedError

    def _schedule_lights_release(self, duration_ms: int) -> None:
        raise NotImplementedError

    def _uses_expression_output(self) -> bool:
        return bool(self._via_expression and self._event_handlers)

    def _notify_expression(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = dict(data or {})
        for handler in list(self._event_handlers):
            try:
                handler(event_type, payload)
            except Exception:
                logger.debug("expression handler failed for %s", event_type, exc_info=True)

    def _render_manual_effect(self, now: float, manual_effect: dict) -> bool:
        if now < self._active_effect_until:
            return True
        if not (bool(manual_effect.get("force")) or self._effect_allowed("manual.effect")):
            self._schedule_lights_release(0)
            return True
        name = str(manual_effect.get("name", "COMET"))
        duration_ms = int(manual_effect.get("duration_ms", 800))
        self._active_effect_until = now + duration_ms / 1000.0
        threading.Thread(
            target=self.neo.play_effect, args=(name, duration_ms),
            kwargs={"color": manual_effect.get("color"), "emotions": manual_effect.get("emotions")},
            daemon=True,
        ).start()
        self._schedule_lights_release(duration_ms)
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
        with self._lock:
            self._last_base = None
        chosen.stamp()
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
            if not eval_condition(rule.when, snapshot) or not rule.ready():
                continue
            if chosen is None or priority_rank(rule.priority) > priority_rank(chosen.priority):
                chosen = rule
        if chosen is None:
            return False
        act = chosen.action or {}
        if self._uses_expression_output():
            chosen.stamp()
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
        if "effect" not in act or now < self._active_effect_until:
            return False
        eff = act.get("effect") or {}
        name = str(eff.get("name", "COMET"))
        duration_ms = int(eff.get("duration_ms", 800))
        event_name = event_name or self._ctx.get("event")
        if not (self._effect_allowed(event_name) and self._claim_lights_for_event(event_name)):
            return True
        self._active_effect_until = now + duration_ms / 1000.0
        chosen.stamp()
        threading.Thread(
            target=self.neo.play_effect, args=(name, duration_ms),
            kwargs={"color": eff.get("color"), "emotions": eff.get("emotions") if isinstance(eff.get("emotions"), list) else None},
            daemon=True,
        ).start()
        self._schedule_lights_release(duration_ms)
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

    def _emit_idle_expression(self) -> None:
        key = ("expression.idle", None)
        if key == self._last_base:
            return
        self._last_base = key
        self._notify_expression("interactions.idle", {"rule": "idle"})
