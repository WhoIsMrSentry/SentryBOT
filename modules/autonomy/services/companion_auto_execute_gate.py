from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


class CompanionAutoExecuteGate:
    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "require_auto_execute_flag": True,
        "min_interval_s": 8.0,
        "allowed_risks": ["none", "low", "medium", "semantic"],
        "blocked_components": [],
        "allowed_priorities": ["low", "normal", "critical"],
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = dict(self.DEFAULTS)
        if isinstance(cfg, dict):
            self.cfg.update(cfg)
        self._last_decision: Dict[str, Any] = {"ok": True, "available": False, "should_execute": False, "reason": "never_checked"}
        self._last_plan_id = ""
        self._last_execute_ts = 0.0

    def status(self) -> Dict[str, Any]:
        return {"ok": True, **self.cfg, "last_decision": dict(self._last_decision)}

    def decide(self, goal_plan: Optional[Dict[str, Any]], *, force: bool = False, now: Optional[float] = None, **_: Any) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        plan = goal_plan if isinstance(goal_plan, dict) else {}
        base = {
            "ok": True,
            "available": bool(plan),
            "should_execute": False,
            "executed": False,
            "force": bool(force),
            "timestamp": ts,
            "plan_id": str(plan.get("plan_id") or ""),
            "behavior": str(plan.get("behavior") or ""),
            "priority": str(plan.get("priority") or "low"),
        }
        if not plan:
            return self._remember(base, "goal_plan_missing")
        if not bool(self.cfg.get("enabled", True)):
            return self._remember(base, "auto_execute_disabled")
        if not bool(plan.get("safe_to_execute", True)):
            return self._remember(base, "goal_marked_unsafe")
        if bool(self.cfg.get("require_auto_execute_flag", True)) and not bool(plan.get("auto_execute", False)) and not force:
            return self._remember(base, "auto_execute_false")
        if str(plan.get("priority") or "low").lower() not in {str(x).lower() for x in self.cfg.get("allowed_priorities", [])}:
            return self._remember(base, "priority_not_allowed")
        allowed, reason = self._actions_allowed(plan)
        if not allowed:
            return self._remember(base, reason)
        plan_id = str(plan.get("plan_id") or "")
        interval = max(0.0, float(self.cfg.get("min_interval_s", 8.0)))
        if not force and plan_id == self._last_plan_id and ts - self._last_execute_ts < interval:
            base["cooldown_remaining_s"] = round(interval - (ts - self._last_execute_ts), 2)
            return self._remember(base, "cooldown")
        base["should_execute"] = True
        base["reason"] = "execute"
        self._last_plan_id = plan_id
        self._last_execute_ts = ts
        self._last_decision = dict(base)
        return dict(base)

    def mark_execution(self, decision: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(decision)
        out["execution"] = execution
        out["executed"] = bool(decision.get("should_execute") and execution.get("applied"))
        out["applied"] = bool(execution.get("applied"))
        out["execution_reason"] = execution.get("reason")
        self._last_decision = dict(out)
        return out

    def _actions_allowed(self, plan: Dict[str, Any]) -> Tuple[bool, str]:
        allowed_risks = {str(x).lower() for x in self.cfg.get("allowed_risks", [])}
        blocked = {str(x).lower() for x in self.cfg.get("blocked_components", [])}
        actions = plan.get("actions") or []
        if not isinstance(actions, list):
            return False, "actions_invalid"
        for action in actions:
            if not isinstance(action, dict):
                continue
            component = str(action.get("component") or action.get("type") or "").lower()
            risk = str(action.get("risk") or "none").lower()
            if component in blocked:
                return False, f"component_blocked:{component}"
            if risk not in allowed_risks:
                return False, f"risk_blocked:{risk}"
        return True, "allowed"

    def _remember(self, base: Dict[str, Any], reason: str) -> Dict[str, Any]:
        out = dict(base)
        out["reason"] = reason
        self._last_decision = out
        return out
