from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .capability_executor import CapabilityExecutor


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalExecutor:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.stop_on_failure = bool(self.cfg.get("stop_on_failure", True))
        self.capabilities = CapabilityExecutor(client) if client is not None else None
        self._last_execution: Dict[str, Any] = {"ok": True, "available": False, "applied": False, "reason": "never_executed"}

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "stop_on_failure": self.stop_on_failure,
            "capability_executor": self.capabilities.status() if self.capabilities is not None else {"ok": False, "reason": "client_missing"},
            "last_execution": dict(self._last_execution),
        }

    def execute(self, goal_plan: Optional[Dict[str, Any]], **_: Any) -> Dict[str, Any]:
        started = time.monotonic()
        plan = _as_dict(goal_plan)
        if not self.enabled:
            return self._remember(False, False, "executor_disabled", plan, [], started)
        if not plan:
            return self._remember(False, False, "goal_plan_missing", plan, [], started)
        if not bool(plan.get("safe_to_execute", True)):
            return self._remember(True, False, "goal_marked_unsafe", plan, [], started)
        if self.capabilities is None:
            return self._remember(True, False, "capability_executor_unavailable", plan, [], started)

        steps = self._steps_for(plan)
        results: List[Dict[str, Any]] = []
        for step in steps:
            result = self.capabilities.execute(step["capability"], step.get("params"))
            result["index"] = step["index"]
            results.append(result)
            if self.stop_on_failure and not result.get("ok"):
                break

        applied = bool(steps) and len(results) == len(steps) and all(bool(item.get("ok")) for item in results)
        reason = "executed" if applied else "execution_failed"
        return self._remember(True, applied, reason, plan, results, started)

    def _remember(
        self,
        available: bool,
        applied: bool,
        reason: str,
        plan: Dict[str, Any],
        results: List[Dict[str, Any]],
        started: float,
    ) -> Dict[str, Any]:
        out = {
            "ok": bool(applied or not available),
            "available": bool(available),
            "applied": bool(applied),
            "reason": reason,
            "plan_id": str(plan.get("plan_id") or ""),
            "behavior": str(plan.get("behavior") or ""),
            "dominant_need": str(plan.get("dominant_need") or ""),
            "recommended_goal": str(plan.get("recommended_goal") or ""),
            "priority": str(plan.get("priority") or "low"),
            "result_count": len(results),
            "results": results,
            "latency_ms": round((time.monotonic() - started) * 1000.0, 2),
            "timestamp": time.time(),
        }
        self._last_execution = dict(out)
        return out

    def _steps_for(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        for index, action in enumerate(plan.get("actions") or [], start=1):
            if not isinstance(action, dict):
                continue
            capability, params = self._translate(action)
            steps.append({"index": index, "capability": capability, "params": params})
        return steps

    @staticmethod
    def _translate(action: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type == "expression":
            return "expression.event", {"event": action.get("event"), "data": action.get("data") or {}}
        if action_type == "motion":
            name = str(action.get("name") or "idle")
            if name == "freeze":
                return "motion.freeze", dict(action)
            return f"motion.{name}", dict(action)
        if action_type == "pose":
            return f"pose.{str(action.get('name') or 'idle')}", dict(action)
        if action_type == "vision":
            mode = str(action.get("mode") or "cheap")
            return ("vision.semantic" if mode == "semantic" else "vision.cheap"), dict(action)
        if action_type == "perception":
            name = str(action.get('name') or 'owner_scan')
            if name in {"track_person", "track_object"}:
                return "perception.track_object", dict(action)
            return f"perception.{name}", dict(action)
        if action_type == "navigation":
            return f"navigation.{str(action.get('name') or 'rest_corner')}", dict(action)
        if action_type == "memory":
            return f"memory.{str(action.get('name') or 'observe')}", dict(action)
        if action_type == "speech":
            mode = str(action.get("mode") or "silent")
            return ("speech.silent" if mode == "silent" else "speech.short_prompt"), dict(action)
        if action_type == "wait":
            return "scheduler.wait", dict(action)
        if action_type == "pet_intent":
            return "semantic.pet_intent", dict(action)
        return "semantic.unknown", dict(action)


__all__ = ["CompanionGoalExecutor"]
