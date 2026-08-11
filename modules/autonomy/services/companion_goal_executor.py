from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .capability_executor import CapabilityExecutor

AUTONOMY_SEMANTIC_NOOP_CONTRACT = True
AUTONOMY_SEMANTIC_NOOP_ROLE = "safe_semantic_passive_goal_step"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalExecutor:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None, client: Any = None) -> None:
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.dry_run_default = bool(self.cfg.get("dry_run_default", True))
        self.allow_real_hardware = bool(self.cfg.get("allow_real_hardware", False))
        self.stop_on_failure = bool(self.cfg.get("stop_on_failure", True))
        self.capabilities = CapabilityExecutor(client) if client is not None else None
        self._last_execution: Dict[str, Any] = {
            "ok": True,
            "available": False,
            "applied": False,
            "reason": "never_executed",
        }

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "dry_run_default": self.dry_run_default,
            "allow_real_hardware": self.allow_real_hardware,
            "stop_on_failure": self.stop_on_failure,
            "capability_executor": (
                self.capabilities.status()
                if self.capabilities is not None
                else {"ok": False, "reason": "client_missing"}
            ),
            "last_execution": dict(self._last_execution),
        }

    def execute(
        self,
        goal_plan: Optional[Dict[str, Any]] = None,
        *,
        dry_run: Optional[bool] = None,
        pc_test: bool = False,
        now: Optional[float] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        plan = _as_dict(goal_plan)
        ts = float(now if now is not None else time.time())
        effective_dry_run = self.dry_run_default if dry_run is None else bool(dry_run)

        if not self.enabled:
            return self._finish(
                False,
                False,
                "executor_disabled",
                plan,
                [],
                started,
                dry_run=effective_dry_run,
                timestamp=ts,
            )
        if not plan:
            return self._finish(
                False,
                False,
                "goal_plan_missing",
                plan,
                [],
                started,
                dry_run=effective_dry_run,
                timestamp=ts,
            )
        if not bool(plan.get("safe_to_execute", True)):
            return self._finish(
                True,
                False,
                "goal_marked_unsafe",
                plan,
                [],
                started,
                dry_run=effective_dry_run,
                timestamp=ts,
            )

        steps = self._build_steps(plan.get("actions") or [])

        if not effective_dry_run and pc_test:
            return self._finish(
                True,
                False,
                "pc_real_execution_blocked",
                plan,
                steps,
                started,
                dry_run=True,
                timestamp=ts,
            )
        if not effective_dry_run and not self.allow_real_hardware:
            return self._finish(
                True,
                False,
                "real_hardware_not_allowed",
                plan,
                steps,
                started,
                dry_run=True,
                timestamp=ts,
            )
        if effective_dry_run or self.capabilities is None:
            return self._finish(
                True,
                False,
                "dry_run" if effective_dry_run else "capability_executor_unavailable",
                plan,
                steps,
                started,
                dry_run=True,
                timestamp=ts,
            )

        results: List[Dict[str, Any]] = []
        for index, step in enumerate(steps, start=1):
            capability = str(step.get("capability") or "")
            if not capability or capability.startswith("semantic.") or step.get("method") == "NOOP":
                result = {
                    "ok": True,
                    "index": index,
                    "capability": capability or "semantic.noop",
                    "reason": "semantic_noop",
                }
            else:
                result = self.capabilities.execute(capability, step.get("params") if isinstance(step.get("params"), dict) else {})
                result["index"] = index
            results.append(result)
            if self.stop_on_failure and not result.get("ok"):
                break

        applied = bool(steps) and len(results) == len(steps) and all(bool(item.get("ok")) for item in results)
        out = self._finish(
            True,
            applied,
            "executed" if applied else "execution_failed",
            plan,
            steps,
            started,
            dry_run=False,
            timestamp=ts,
        )
        out["results"] = results
        out["result_count"] = len(results)
        self._last_execution = dict(out)
        return out

    def _finish(
        self,
        available: bool,
        applied: bool,
        reason: str,
        plan: Dict[str, Any],
        steps: List[Dict[str, Any]],
        started: float,
        *,
        dry_run: bool,
        timestamp: float,
    ) -> Dict[str, Any]:
        out = {
            "ok": True,
            "available": bool(available),
            "applied": bool(applied),
            "reason": reason,
            "dry_run": bool(dry_run),
            "plan_id": str(plan.get("plan_id") or ""),
            "behavior": str(plan.get("behavior") or ""),
            "dominant_need": str(plan.get("dominant_need") or ""),
            "recommended_goal": str(plan.get("recommended_goal") or ""),
            "priority": str(plan.get("priority") or "low"),
            "steps": steps,
            "step_count": len(steps),
            "latency_ms": round((time.monotonic() - started) * 1000.0, 2),
            "timestamp": timestamp,
        }
        self._last_execution = dict(out)
        return out

    def _build_steps(self, actions: Any) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        for index, action in enumerate(actions if isinstance(actions, list) else [], start=1):
            if not isinstance(action, dict):
                continue
            step = self._translate_step(action)
            step["index"] = index
            steps.append(step)
        return steps

    @staticmethod
    def _translate_step(action: Dict[str, Any]) -> Dict[str, Any]:
        # Handle raw LLM tool calls
        tool = str(action.get("tool") or "").strip().lower()
        if tool:
            if tool == "speak":
                return {
                    "component": "speak",
                    "method": "POST",
                    "url": "/speak/say",
                    "risk": "low",
                    "capability": "speech.short_prompt",
                    "params": dict(action),
                    "payload": dict(action),
                }
            if tool == "move_head":
                return {
                    "component": "piservo",
                    "method": "POST",
                    "url": "/piservo/move_head",
                    "risk": "low",
                    "capability": "motion.head",
                    "params": dict(action),
                    "payload": dict(action),
                }
            if tool == "oled_face":
                return {
                    "component": "expression",
                    "method": "POST",
                    "url": "/expression/face",
                    "risk": "none",
                    "capability": "expression.face",
                    "params": dict(action),
                    "payload": dict(action),
                }
            if tool == "set_lights":
                return {
                    "component": "expression",
                    "method": "POST",
                    "url": "/expression/lights",
                    "risk": "none",
                    "capability": "expression.lights",
                    "params": dict(action),
                    "payload": dict(action),
                }

        action_type = str(action.get("type") or "").strip().lower()
        if action_type == "expression":
            event = action.get("event")
            return {
                "component": "expression",
                "method": "POST",
                "url": "/expression/event",
                "risk": "none",
                "capability": "expression.event",
                "params": {"event": event, "data": action.get("data") or {}},
                "payload": dict(action),
            }
        if action_type == "vision":
            mode = str(action.get("mode") or "cheap").strip().lower()
            return {
                "component": "vlm_bridge",
                "method": "POST" if mode == "semantic" else "GET",
                "url": "/vlm/context/refresh" if mode == "semantic" else "/vlm/results/latest",
                "risk": "low",
                "capability": "vision.semantic" if mode == "semantic" else "vision.cheap",
                "params": dict(action),
                "payload": dict(action),
            }
        if action_type == "motion":
            name = str(action.get("name") or "idle").strip() or "idle"
            if name == "freeze":
                return {
                    "component": "animate",
                    "method": "POST",
                    "url": "/animate/stop",
                    "risk": str(action.get("risk") or "low"),
                    "capability": "motion.freeze",
                    "params": dict(action),
                    "payload": dict(action),
                }
            return {
                "component": "piservo",
                "method": "POST",
                "url": f"/piservo/gesture?name={name}",
                "risk": str(action.get("risk") or "low"),
                "capability": f"motion.{name}",
                "params": dict(action),
                "payload": dict(action),
            }
        if action_type == "pose":
            name = str(action.get("name") or "idle").strip() or "idle"
            return {
                "component": "animate",
                "method": "POST",
                "url": f"/animate/run?name={name}",
                "risk": str(action.get("risk") or "low"),
                "capability": f"pose.{name}",
                "params": dict(action),
                "payload": dict(action),
            }
        if action_type == "wait":
            return {
                "component": "scheduler",
                "method": "NOOP",
                "url": "noop:wait",
                "risk": "none",
                "capability": "scheduler.wait",
                "params": dict(action),
                "payload": dict(action),
            }
        if action_type == "speech":
            mode = str(action.get("mode") or "silent").strip().lower()
            return {
                "component": "speak",
                "method": "NOOP" if mode == "silent" else "POST",
                "url": "noop:speech" if mode == "silent" else "/speak/say",
                "risk": "none",
                "capability": "speech.silent" if mode == "silent" else "speech.short_prompt",
                "params": dict(action),
                "payload": dict(action),
            }
        if action_type == "pet_intent":
            return {
                "component": "semantic",
                "method": "NOOP",
                "url": "noop:pet_intent",
                "risk": "none",
                "capability": "semantic.pet_intent",
                "params": dict(action),
                "payload": dict(action),
            }
        return {
            "component": "unknown",
            "method": "NOOP",
            "url": "noop:unknown_action",
            "risk": "none",
            "capability": "semantic.unknown",
            "params": dict(action),
            "payload": dict(action),
        }


__all__ = [
    "AUTONOMY_SEMANTIC_NOOP_CONTRACT",
    "AUTONOMY_SEMANTIC_NOOP_ROLE",
    "CompanionGoalExecutor",
]
