from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .capability_executor import CapabilityExecutor
from .companion_goal_translator import CompanionGoalTranslatorMixin

AUTONOMY_SEMANTIC_NOOP_CONTRACT = True
AUTONOMY_SEMANTIC_NOOP_ROLE = "safe_semantic_passive_goal_step"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalExecutor(CompanionGoalTranslatorMixin):
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

        guard = _as_dict(plan.get("capability_guard"))
        if bool(self.cfg.get("require_capability_guard", False)) and guard:
            blocked = bool(guard.get("blocked", False) or guard.get("available") is False)
            if blocked:
                return self._finish(
                    True,
                    False,
                    "capability_guard_blocked",
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


__all__ = [
    "AUTONOMY_SEMANTIC_NOOP_CONTRACT",
    "AUTONOMY_SEMANTIC_NOOP_ROLE",
    "CompanionGoalExecutor",
]
