from __future__ import annotations

import time
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_output_planner import build_pet_output_plan

PET_COMPANION_BEHAVIOR_LOOP_INTEGRATION_CONTRACT = True
PET_OUTPUT_PLANNER_BEHAVIOR_LOOP_INTEGRATION_CONTRACT = True


class CompanionBehaviorLoop:
    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "interval_s": 10.0,
        "min_idle_s": 5.0,
        "skip_when_sleeping": False,
        "skip_when_speech_busy": True,
        "history_limit": 20,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self._last_tick_ts = 0.0
        self._last_decision: Dict[str, Any] = {"ok": True, "available": False, "should_tick": False, "reason": "never_checked"}

    def status(self) -> Dict[str, Any]:
        return {"ok": True, **self.cfg, "last_decision": dict(self._last_decision)}

    def decide(
        self,
        *,
        needs: Optional[Dict[str, Any]] = None,
        goal: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
        sleeping: bool = False,
        speech_busy: bool = False,
        force: bool = False,
        **_: Any,
    ) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        needs_map = needs if isinstance(needs, dict) else {}
        goal_map = goal if isinstance(goal, dict) else {}
        idle_s = float(needs_map.get("idle_s") or 0.0)
        pet = goal_map.get("pet_companion") if isinstance(goal_map.get("pet_companion"), dict) else {}
        output_plan = build_pet_output_plan(pet)
        base = {
            "ok": True,
            "available": bool(goal_map),
            "should_tick": False,
            "executed": False,
            "timestamp": ts,
            "idle_s": round(idle_s, 2),
            "plan_id": str(goal_map.get("plan_id") or ""),
            "dominant_need": str(goal_map.get("dominant_need") or ""),
            "behavior": str(goal_map.get("behavior") or ""),
            "priority": str(goal_map.get("priority") or "low"),
            "pet_output_plan": output_plan,
        }
        if not bool(self.cfg.get("enabled", True)):
            return self._remember(base, "behavior_loop_disabled")
        if not goal_map:
            return self._remember(base, "goal_missing")
        if bool(self.cfg.get("skip_when_sleeping", False)) and sleeping:
            return self._remember(base, "sleeping")
        if bool(self.cfg.get("skip_when_speech_busy", True)) and speech_busy:
            return self._remember(base, "speech_busy")
        if not force and idle_s < float(self.cfg.get("min_idle_s", 5.0)):
            return self._remember(base, "idle_too_fresh")
        interval = max(1.0, float(self.cfg.get("interval_s", 10.0)))
        if not force and ts - self._last_tick_ts < interval:
            base["cooldown_remaining_s"] = round(interval - (ts - self._last_tick_ts), 2)
            return self._remember(base, "cooldown")
        base["should_tick"] = True
        base["reason"] = "scheduled"
        self._last_tick_ts = ts
        self._last_decision = dict(base)
        return dict(base)

    def mark_execution(self, decision: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(decision)
        out["execution"] = execution
        out["executed"] = bool(execution.get("applied"))
        out["applied"] = bool(execution.get("applied"))
        out["execution_reason"] = execution.get("reason")
        self._last_decision = dict(out)
        return out

    def _remember(self, base: Dict[str, Any], reason: str) -> Dict[str, Any]:
        out = dict(base)
        out["reason"] = reason
        self._last_decision = out
        return out
