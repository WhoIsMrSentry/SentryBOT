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
        self.decision_traces = None
        self.goal_store = None
        self._last_execution: Dict[str, Any] = {
            "ok": True,
            "available": False,
            "applied": False,
            "reason": "never_executed",
        }

    def set_decision_traces(self, store: Any) -> None:
        """Share AgentOrchestrator decision trace store for unified observability."""
        self.decision_traces = store

    def set_goal_store(self, store: Any) -> None:
        """Share in-process GoalStore for cross-tick companion continuity."""
        self.goal_store = store

    def _cognitive_loop_enabled(self) -> bool:
        loop_cfg = self.cfg.get("cognitive_loop", {}) if isinstance(self.cfg.get("cognitive_loop"), dict) else {}
        return bool(loop_cfg.get("enabled", True))

    def _loop_cfg(self) -> Dict[str, Any]:
        loop_cfg = self.cfg.get("cognitive_loop", {}) if isinstance(self.cfg.get("cognitive_loop"), dict) else {}
        out = dict(loop_cfg)
        # Allow nested Batch 4 blocks at executor root or under cognitive_loop
        for key in ("contextual_replan", "goal_persistence"):
            if key not in out and isinstance(self.cfg.get(key), dict):
                out[key] = dict(self.cfg.get(key))
        return out

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "dry_run_default": self.dry_run_default,
            "allow_real_hardware": self.allow_real_hardware,
            "stop_on_failure": self.stop_on_failure,
            "cognitive_loop_enabled": self._cognitive_loop_enabled(),
            "goal_store_enabled": self.goal_store is not None,
            "capability_executor": (
                self.capabilities.status()
                if self.capabilities is not None
                else {"ok": False, "reason": "client_missing"}
            ),
            "last_execution": dict(self._last_execution),
        }

    def _simulate_on_dry_run(self) -> bool:
        loop_cfg = self._loop_cfg()
        return bool(loop_cfg.get("simulate_on_dry_run", True))

    def _can_simulate_cognitive(self, *, effective_dry_run: bool) -> bool:
        """Batch 6b: dry-run / no-hardware may still advance GoalStore via simulated loop."""
        if not self._cognitive_loop_enabled():
            return False
        if self.goal_store is None:
            return False
        if not self._simulate_on_dry_run():
            return False
        return bool(effective_dry_run or self.capabilities is None or not self.allow_real_hardware)

    @staticmethod
    def _simulated_capability_execute(capability: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "ok": True,
            "capability": str(capability or ""),
            "params": dict(params or {}),
            "reason": "dry_run_simulated",
            "dry_run": True,
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

        # PC / no-hardware: prefer GoalStore simulation when available; else legacy dry-run reasons.
        forced_reason = None
        if not effective_dry_run and pc_test:
            effective_dry_run = True
            forced_reason = "pc_real_execution_blocked"
        elif not effective_dry_run and not self.allow_real_hardware:
            effective_dry_run = True
            forced_reason = "real_hardware_not_allowed"

        if self._cognitive_loop_enabled() and not effective_dry_run and self.capabilities is not None:
            return self._execute_cognitive_loop(
                plan,
                steps,
                started,
                timestamp=ts,
                execute_capability=self.capabilities.execute,
                dry_run=False,
            )

        if self._can_simulate_cognitive(effective_dry_run=effective_dry_run):
            return self._execute_cognitive_loop(
                plan,
                steps,
                started,
                timestamp=ts,
                execute_capability=self._simulated_capability_execute,
                dry_run=True,
            )

        if forced_reason is not None:
            return self._finish(
                True,
                False,
                forced_reason,
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

        return self._execute_linear(plan, steps, started, timestamp=ts)

    def _execute_cognitive_loop(
        self,
        plan: Dict[str, Any],
        steps: List[Dict[str, Any]],
        started: float,
        *,
        timestamp: float,
        execute_capability: Any = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        from modules.agent_core.services.runtime.companion_execution_loop import CompanionExecutionLoop

        loop_cfg = self._loop_cfg()
        loop = CompanionExecutionLoop(
            traces=self.decision_traces,
            cfg=loop_cfg,
            goal_store=self.goal_store,
        )
        cap_fn = execute_capability
        if cap_fn is None:
            if self.capabilities is None:
                cap_fn = self._simulated_capability_execute
            else:
                cap_fn = self.capabilities.execute
        loop_result = loop.run(
            plan,
            steps,
            execute_capability=cap_fn,
            goal_id=str((plan.get("typed_goal") or {}).get("id") or plan.get("plan_id") or ""),
        )
        applied = bool(loop_result.get("applied"))
        reason = str(loop_result.get("reason") or ("executed" if applied else "execution_failed"))
        if dry_run and applied:
            reason = "dry_run_simulated"
        out = self._finish(
            True,
            applied,
            reason,
            plan,
            steps,
            started,
            dry_run=bool(dry_run),
            timestamp=timestamp,
        )
        out["results"] = list(loop_result.get("results") or [])
        out["result_count"] = len(out["results"])
        out["cognitive_loop"] = {
            "state": loop_result.get("state"),
            "stop_reason": loop_result.get("stop_reason"),
            "observations": loop_result.get("observations"),
            "usage": loop_result.get("usage"),
            "typed_plan": loop_result.get("plan"),
            "goal": loop_result.get("goal"),
            "goal_snapshot": loop_result.get("goal_snapshot"),
            "simulated": bool(dry_run),
        }
        self._last_execution = dict(out)
        return out

    def _execute_linear(
        self,
        plan: Dict[str, Any],
        steps: List[Dict[str, Any]],
        started: float,
        *,
        timestamp: float,
    ) -> Dict[str, Any]:
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
                result = self.capabilities.execute(
                    capability,
                    step.get("params") if isinstance(step.get("params"), dict) else {},
                )
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
            timestamp=timestamp,
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
