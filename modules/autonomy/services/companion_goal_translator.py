from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.companion_goal_translator")


class CompanionGoalTranslatorMixin:
    """Step translation, action mapping, and execution result finishing."""

    cfg: Dict[str, Any]
    _last_execution: Dict[str, Any]

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
        lifecycle_cfg = self.cfg.get("lifecycle", {})
        lifecycle_cfg = lifecycle_cfg if isinstance(lifecycle_cfg, dict) else {}
        if bool(lifecycle_cfg.get("enabled", False)):
            cancelled = {str(item) for item in lifecycle_cfg.get("cancelled_reasons", []) if str(item)}
            if reason in cancelled:
                state = "cancelled"
            elif dry_run:
                state = str(lifecycle_cfg.get("dry_run_state") or "simulated")
            elif applied:
                state = str(lifecycle_cfg.get("applied_state") or "completed")
            elif not available:
                state = str(lifecycle_cfg.get("unavailable_state") or "blocked")
            else:
                state = str(lifecycle_cfg.get("failure_state") or "failed")
            out["lifecycle"] = {
                "state": state,
                "plan_id": out.get("plan_id"),
                "reason": reason,
                "updated_at": timestamp,
            }
            recovery_cfg = self.cfg.get("recovery_ladder", {})
            recovery_cfg = recovery_cfg if isinstance(recovery_cfg, dict) else {}
            if state in {"blocked", "failed"} and bool(recovery_cfg.get("enabled", False)):
                out["recovery"] = {
                    "states": [str(item) for item in recovery_cfg.get("states", []) if str(item)],
                    "max_attempts": int(recovery_cfg.get("max_attempts", 0) or 0),
                    "terminal_semantic": str(recovery_cfg.get("terminal_semantic") or ""),
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
            semantic = str(action.get("semantic") or "").strip()
            if semantic:
                return {
                    "component": "neopixel",
                    "method": "POST",
                    "url": "/neopixel/companion/semantic",
                    "risk": "none",
                    "capability": "expression.semantic_face",
                    "params": {"semantic": semantic, "revision": str(action.get("revision") or "")},
                    "payload": {"semantic": semantic, "revision": str(action.get("revision") or "")},
                }
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
        if action_type == "navigation":
            policy = str(action.get("policy") or "").strip()
            if not policy:
                return {
                    "component": "navigation",
                    "method": "NOOP",
                    "url": "noop:navigation_policy_missing",
                    "risk": "none",
                    "capability": "navigation.policy_missing",
                    "params": dict(action),
                    "payload": dict(action),
                }
            payload = dict(action)
            payload["companion_policy"] = policy
            return {
                "component": "autonomy",
                "method": "POST",
                "url": "/autonomy/navigation/goal",
                "risk": str(action.get("risk") or "low"),
                "capability": f"navigation.{policy}",
                "params": dict(action),
                "payload": payload,
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
