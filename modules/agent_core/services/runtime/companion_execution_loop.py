"""Embodied companion plan execution through the shared cognitive loop.

Executes registry capabilities step-by-step with Observation → Evaluation →
Recovery → optional Replan. Does not duplicate recovery logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .capability_index import CapabilityIndex
from .contextual_replanner import ContextualReplanner, LLMAssistFn
from .decision_trace import DecisionTraceStore
from .goal_store import GoalStore
from .plan_policy_gate import ApprovedPlan, PlanPolicyGate, Reject
from .progress_tracker import ProgressTracker
from .recovery import FailureClassifier, RecoveryManager
from .schemas import (
    Budget,
    CandidatePlan,
    Evaluation,
    FailureClass,
    Goal,
    GoalSnapshot,
    GoalStatus,
    Observation,
    Plan,
    PlanStep,
    PolicyConstraints,
    ReplanContext,
    RuntimeBudgetUsage,
    RuntimeState,
    StepStatus,
)

logger = logging.getLogger("agent.companion_loop")

CapabilityExecuteFn = Callable[[str, Dict[str, Any]], Dict[str, Any]]

# Capabilities safe to retry / substitute without duplicating side effects.
READ_ONLY_CAPABILITIES = frozenset(
    {
        "vision.cheap",
        "vision.semantic",
        "memory.observe",
        "scheduler.wait",
        "speech.silent",
        "semantic.pet_intent",
        "semantic.unknown",
    }
)

CAPABILITY_ALTERNATES: Dict[str, List[str]] = {
    "vision.cheap": ["vision.semantic"],
    "perception.track_object": ["vision.cheap"],
    "perception.owner_scan": ["vision.cheap"],
}


def classify_capability_result(result: Dict[str, Any]) -> FailureClass:
    if bool(result.get("ok")):
        return FailureClass.NONE
    reason = str(result.get("reason") or result.get("error") or "").lower()
    if "capability_not_found" in reason or "capability_disabled" in reason:
        return FailureClass.TOOL_UNAVAILABLE
    if reason.startswith("risk_blocked"):
        return FailureClass.UNSAFE_ACTION
    if "handler_exception" in reason or "timeout" in reason:
        return FailureClass.TEMPORARY
    if any(token in reason for token in ("obstacle", "blocked", "collision", "path_blocked")):
        return FailureClass.UNEXPECTED_RESULT
    if "handler_failed" in reason:
        return FailureClass.UNEXPECTED_RESULT
    return FailureClass.UNKNOWN


def observation_replan(plan: Plan, failed_step: PlanStep, failure_class: FailureClass) -> Optional[Plan]:
    """Replace invalid movement/perception tail with observe-and-wait."""
    failed_cap = (
        str(failed_step.required_capabilities[0])
        if failed_step.required_capabilities
        else str(failed_step.metadata.get("capability") or "")
    )
    failed_step.status = StepStatus.FAILED

    should_replan = (
        failed_cap.startswith("navigation.")
        or failed_cap.startswith("motion.")
        or (
            failure_class in {FailureClass.INVALID_PLAN, FailureClass.UNEXPECTED_RESULT}
            and failed_cap.startswith("perception.")
        )
    )
    if not should_replan:
        return None

    for step in plan.steps:
        if step.id == failed_step.id:
            continue
        if step.status not in {StepStatus.PENDING, StepStatus.READY}:
            continue
        cap = str(step.required_capabilities[0]) if step.required_capabilities else ""
        if cap.startswith(("navigation.", "motion.", "perception.", "pose.")):
            step.status = StepStatus.SKIPPED
            step.metadata["skipped_reason"] = "replan_after_blocked_step"

    observe = PlanStep(
        objective="Observe after execution failure",
        required_capabilities=["vision.cheap"],
        status=StepStatus.READY,
        metadata={
            "action": {"type": "vision", "mode": "cheap", "reason": "replan_observe"},
            "risk": "none",
            "replan": True,
        },
    )
    wait = PlanStep(
        objective="Wait after replan",
        required_capabilities=["scheduler.wait"],
        dependencies=[observe.id],
        status=StepStatus.READY,
        metadata={
            "action": {"type": "wait", "label": "replan_wait"},
            "risk": "none",
            "replan": True,
        },
    )
    plan.steps.extend([observe, wait])
    plan.version += 1
    plan.metadata["replanned"] = True
    plan.metadata["replan_reason"] = f"observation:{failed_cap}:{failure_class.value}"
    return plan


class CompanionExecutionLoop:
    """Run typed companion plans with shared runtime recovery primitives."""

    def __init__(
        self,
        *,
        traces: Optional[DecisionTraceStore] = None,
        classifier: Optional[FailureClassifier] = None,
        recovery: Optional[RecoveryManager] = None,
        capabilities: Optional[CapabilityIndex] = None,
        progress: Optional[ProgressTracker] = None,
        budget: Optional[Budget] = None,
        cfg: Optional[Dict[str, Any]] = None,
        goal_store: Optional[GoalStore] = None,
        replanner: Optional[ContextualReplanner] = None,
        policy_gate: Optional[PlanPolicyGate] = None,
        llm_assist_fn: Optional[LLMAssistFn] = None,
        policy_constraints: Optional[PolicyConstraints] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        replan_cfg = raw.get("contextual_replan") if isinstance(raw.get("contextual_replan"), dict) else raw
        self.cfg = raw
        self.traces = (
            traces
            if traces is not None
            else DecisionTraceStore(maxlen=int(raw.get("decision_trace_maxlen", 64)))
        )
        self.classifier = classifier or FailureClassifier()
        self.recovery = recovery or RecoveryManager()
        self.capabilities = capabilities if capabilities is not None else CapabilityIndex.from_robot_registry()
        self.progress = progress or ProgressTracker(
            max_identical=int(raw.get("max_identical_actions", 3)),
            max_zero_progress=int(raw.get("max_zero_progress", 3)),
        )
        self.budget = budget or Budget(
            max_iterations=int(raw.get("max_iterations", 12)),
            max_retries=int(raw.get("max_retries", 2)),
            max_replans=int(raw.get("max_replans", 2)),
        )
        self.goal_store = goal_store
        self.contextual_replan_enabled = bool(replan_cfg.get("enabled", True))
        self.replanner = replanner or ContextualReplanner(
            capabilities=self.capabilities,
            cfg=replan_cfg,
            llm_assist_fn=llm_assist_fn,
        )
        self.policy_gate = policy_gate or PlanPolicyGate(capabilities=self.capabilities, cfg=replan_cfg)
        self.policy_constraints = policy_constraints or PolicyConstraints(
            max_steps=int(replan_cfg.get("max_candidate_steps", 4)),
            risk_ceiling=str(replan_cfg.get("risk_ceiling") or "medium"),
            blocked_risks=list(replan_cfg.get("blocked_risks") or ["critical"]),
        )
        self.usage = RuntimeBudgetUsage()
        self.state = RuntimeState.IDLE
        self._retry_counts: Dict[str, int] = {}
        self._recovery_history: List[Dict[str, Any]] = []
        self._goal_plan_ref: Dict[str, Any] = {}

    def run(
        self,
        goal_plan: Dict[str, Any],
        steps: Sequence[Dict[str, Any]],
        *,
        execute_capability: CapabilityExecuteFn,
        goal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._goal_plan_ref = goal_plan if isinstance(goal_plan, dict) else {}
        prior_usage = self._goal_plan_ref.get("_runtime_budget_usage") or self._goal_plan_ref.get("budget_usage")
        if isinstance(prior_usage, dict) and prior_usage:
            self.usage = RuntimeBudgetUsage.from_dict(prior_usage)
        else:
            self.usage = RuntimeBudgetUsage()
        self.progress.reset()
        prior_sigs = self._goal_plan_ref.get("_progress_signatures") or []
        if prior_sigs:
            self.progress.restore(
                prior_sigs,
                zero_progress=int(self._goal_plan_ref.get("_zero_progress") or 0),
            )
        self._retry_counts.clear()
        self._recovery_history = list(self._goal_plan_ref.get("_recovery_history") or [])
        self.state = RuntimeState.OBSERVING

        goal, plan = self._resolve_goal_plan(goal_plan, steps, goal_id=goal_id)
        goal.status = GoalStatus.ACTIVE

        observations: List[Dict[str, Any]] = []
        step_results: List[Dict[str, Any]] = []
        stop_reason = ""
        applied = False
        self._used_translated: set = set()
        last_observation: Optional[Dict[str, Any]] = None
        last_evaluation: Optional[Dict[str, Any]] = None

        while True:
            exceeded = self.usage.exceeded(self.budget)
            if exceeded:
                remaining = any(
                    s.status in {StepStatus.PENDING, StepStatus.READY} for s in plan.steps
                )
                if remaining and exceeded in {"max_iterations", "max_execution_time"}:
                    self.state = RuntimeState.WAITING_FOR_INPUT
                    goal.status = GoalStatus.WAITING
                    stop_reason = exceeded
                else:
                    self.state = RuntimeState.BUDGET_EXCEEDED
                    stop_reason = exceeded
                    goal.status = GoalStatus.FAILED
                break

            self.usage.iterations += 1
            plan_step = plan.next_ready_step() if plan else None
            if plan_step is None:
                required_steps = [
                    s for s in plan.steps if s.status not in {StepStatus.SKIPPED}
                ]
                applied = bool(required_steps) and all(
                    s.status == StepStatus.SUCCEEDED for s in required_steps
                )
                self.state = RuntimeState.COMPLETED if applied else RuntimeState.FAILED
                goal.status = GoalStatus.COMPLETED if applied else GoalStatus.FAILED
                stop_reason = "completed" if applied else "plan_exhausted"
                break

            exec_step, capability, params = self._resolve_execution_step(plan_step, steps)
            plan_step.status = StepStatus.RUNNING
            signature = f"{capability}:{sorted((params or {}).items())}"

            raw_result = self._execute_step(exec_step, capability, params, execute_capability)
            step_results.append(raw_result)

            success = bool(raw_result.get("ok"))
            failure = classify_capability_result(raw_result)
            observation = Observation(
                source=f"capability.{capability or 'semantic'}",
                result=raw_result,
                success=success,
                confidence=0.9 if success else 0.2,
                action_id=plan_step.id,
                metadata={"capability": capability, "failure_class": failure.value},
            )
            obs_dict = observation.to_dict()
            observations.append(obs_dict)
            last_observation = obs_dict

            evaluation = Evaluation(
                execution_success=success,
                goal_success=False,
                should_replan=failure
                in {FailureClass.INVALID_PLAN, FailureClass.UNEXPECTED_RESULT, FailureClass.INSUFFICIENT_CONTEXT},
                confidence=observation.confidence,
                reason="ok" if success else failure.value,
                failure_class=failure,
            )
            last_evaluation = evaluation.to_dict()

            stall = self.progress.record(signature, progressed=success)
            if stall:
                self.state = RuntimeState.FAILED
                goal.status = GoalStatus.FAILED
                stop_reason = stall
                self._trace(goal.id, plan_step, capability, evaluation, stop_reason, raw_result)
                break

            self._trace(goal.id, plan_step, capability, evaluation, "continue" if success else "recover", raw_result)

            if success:
                plan_step.status = StepStatus.SUCCEEDED
                continue

            plan_step.status = StepStatus.FAILED
            recovery = self._recovery_for(failure, capability, plan_step.id)
            handled = self._apply_recovery(
                recovery,
                goal=goal,
                plan=plan,
                failed_step=plan_step,
                failure=failure,
                capability=capability,
                params=params,
                observation=observation,
                evaluation=evaluation,
                execute_capability=execute_capability,
                step_results=step_results,
                observations=observations,
            )
            if handled.get("continue_failure"):
                continue
            if handled.get("stop"):
                stop_reason = str(handled.get("reason") or "recovery_stop")
                if stop_reason == "ask_user" or recovery.should_ask_user:
                    goal.status = GoalStatus.WAITING
                    self.state = RuntimeState.WAITING_FOR_INPUT
                else:
                    goal.status = GoalStatus.FAILED if recovery.should_abort else GoalStatus.WAITING
                    self.state = RuntimeState.FAILED if recovery.should_abort else RuntimeState.WAITING_FOR_INPUT
                applied = bool(handled.get("applied"))
                break
            if handled.get("replanned"):
                self.usage.replans += 1
                goal.status = GoalStatus.ACTIVE
                continue
            if handled.get("retried") or handled.get("switched"):
                continue

            stop_reason = recovery.reason or "unhandled_failure"
            goal.status = GoalStatus.FAILED
            self.state = RuntimeState.FAILED
            break

        snapshot = self._persist_snapshot(
            goal,
            plan,
            goal_plan=self._goal_plan_ref,
            last_observation=last_observation,
            last_evaluation=last_evaluation,
        )

        return {
            "ok": True,
            "applied": applied,
            "reason": "executed" if applied else (stop_reason or "execution_failed"),
            "stop_reason": stop_reason,
            "state": self.state.value,
            "goal": goal.to_dict(),
            "plan": plan.to_dict() if plan else None,
            "results": step_results,
            "observations": observations,
            "usage": {
                "iterations": self.usage.iterations,
                "retries": self.usage.retries,
                "replans": self.usage.replans,
                "tool_calls": self.usage.tool_calls,
            },
            "trace_count": len(self.traces),
            "goal_snapshot": snapshot.to_dict() if snapshot else None,
        }

    def _resolve_goal_plan(
        self,
        goal_plan: Dict[str, Any],
        steps: Sequence[Dict[str, Any]],
        *,
        goal_id: Optional[str],
    ) -> Tuple[Goal, Plan]:
        typed_goal = goal_plan.get("typed_goal")
        typed_plan = goal_plan.get("typed_plan")
        if isinstance(typed_goal, dict) and isinstance(typed_plan, dict):
            goal = Goal.from_dict(typed_goal)
            plan = Plan.from_dict(typed_plan)
            return goal, plan

        gid = goal_id or str(goal_plan.get("plan_id") or "companion_goal")
        goal = Goal(
            id=gid,
            objective=str(goal_plan.get("behavior") or "companion goal"),
            metadata={
                "dominant_need": goal_plan.get("dominant_need"),
                "recommended_goal": goal_plan.get("recommended_goal"),
            },
        )
        plan_steps: List[PlanStep] = []
        prev: Optional[str] = None
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            capability = str(step.get("capability") or "")
            action = step.get("payload") if isinstance(step.get("payload"), dict) else {}
            if not action and isinstance(step.get("params"), dict):
                action = dict(step.get("params"))
            ps = PlanStep(
                objective=str(step.get("objective") or capability or f"step_{index}"),
                required_capabilities=[capability] if capability else [],
                dependencies=[prev] if prev else [],
                status=StepStatus.READY,
                metadata={"action": action, "translated_step": step, "risk": str(step.get("risk") or "low")},
            )
            plan_steps.append(ps)
            prev = ps.id
        return goal, Plan(goal_id=goal.id, steps=plan_steps)

    def _resolve_execution_step(
        self,
        plan_step: PlanStep,
        translated_steps: Sequence[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        action = dict(plan_step.metadata.get("action") or {})
        capability = (
            str(plan_step.required_capabilities[0])
            if plan_step.required_capabilities
            else str(action.get("capability") or "")
        )
        translated = plan_step.metadata.get("translated_step")
        if isinstance(translated, dict):
            exec_step = translated
            params = dict(translated.get("params") or {})
        else:
            exec_step = None
            for idx, step in enumerate(translated_steps):
                if idx in self._used_translated:
                    continue
                step_cap = str(step.get("capability") or "")
                if capability and step_cap == capability:
                    self._used_translated.add(idx)
                    exec_step = step
                    break
            if exec_step is None:
                exec_step = action
            params = dict(exec_step.get("params") or exec_step.get("payload") or action)
        if not capability:
            capability = str(exec_step.get("capability") or action.get("capability") or "semantic.noop")
        return exec_step if isinstance(exec_step, dict) else action, capability, params

    def _execute_step(
        self,
        exec_step: Dict[str, Any],
        capability: str,
        params: Dict[str, Any],
        execute_capability: CapabilityExecuteFn,
    ) -> Dict[str, Any]:
        if (
            not capability
            or capability.startswith("semantic.")
            or str(exec_step.get("method") or "").upper() == "NOOP"
        ):
            return {
                "ok": True,
                "capability": capability or "semantic.noop",
                "reason": "semantic_noop",
                "index": len(params),
            }
        if not self.capabilities.is_capability_enabled(capability):
            return {"ok": False, "capability": capability, "reason": "capability_disabled"}
        return execute_capability(capability, params)

    def _recovery_for(self, failure: FailureClass, capability: str, step_id: str):
        alts = [c for c in CAPABILITY_ALTERNATES.get(capability, []) if self.capabilities.is_capability_enabled(c)]
        attempt = int(self._retry_counts.get(step_id, 0))
        return self.recovery.decide(
            failure,
            attempt=attempt,
            max_retries=self.budget.max_retries,
            alternate_tools=alts,
            has_plan=True,
        )

    def _apply_recovery(
        self,
        recovery,
        *,
        goal: Goal,
        plan: Plan,
        failed_step: PlanStep,
        failure: FailureClass,
        capability: str,
        params: Dict[str, Any],
        observation: Observation,
        evaluation: Evaluation,
        execute_capability: CapabilityExecuteFn,
        step_results: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if recovery.should_abort:
            return {"stop": True, "reason": recovery.reason or "abort", "applied": False}

        if (
            recovery.should_retry
            and capability in READ_ONLY_CAPABILITIES
            and self._retry_counts.get(failed_step.id, 0) < self.budget.max_retries
        ):
            self._retry_counts[failed_step.id] = self._retry_counts.get(failed_step.id, 0) + 1
            self.usage.retries += 1
            failed_step.status = StepStatus.READY
            retry = self._execute_step(
                dict(failed_step.metadata.get("translated_step") or failed_step.metadata.get("action") or {}),
                capability,
                params,
                execute_capability,
            )
            step_results.append({**retry, "recovery": "retry"})
            if retry.get("ok"):
                failed_step.status = StepStatus.SUCCEEDED
                observations.append(
                    Observation(
                        source=f"capability.{capability}",
                        result=retry,
                        success=True,
                        action_id=failed_step.id,
                        metadata={"recovery": "retry"},
                    ).to_dict()
                )
                return {"retried": True, "applied": False}
            return {"retried": True, "applied": False}

        if recovery.should_switch_tool and recovery.alternate_tool:
            alt = str(recovery.alternate_tool)
            if alt in READ_ONLY_CAPABILITIES and self.capabilities.is_capability_enabled(alt):
                alt_params = dict(params)
                alt_params["reason"] = alt_params.get("reason") or "recovery_switch"
                alt_result = execute_capability(alt, alt_params)
                step_results.append({**alt_result, "recovery": "switch_capability", "alternate": alt})
                observations.append(
                    Observation(
                        source=f"capability.{alt}",
                        result=alt_result,
                        success=bool(alt_result.get("ok")),
                        action_id=failed_step.id,
                        metadata={"recovery": "switch_capability", "from": capability},
                    ).to_dict()
                )
                if alt_result.get("ok"):
                    failed_step.status = StepStatus.SUCCEEDED
                    failed_step.metadata["recovered_via"] = alt
                    return {"switched": True, "applied": False}
                return {"switched": True, "applied": False}

        if recovery.should_replan and self.usage.replans < self.budget.max_replans:
            applied_replan = self._contextual_replan(
                goal=goal,
                plan=plan,
                failed_step=failed_step,
                failure=failure,
                observation=observation,
                evaluation=evaluation,
            )
            if applied_replan:
                return {"replanned": True, "applied": False}

        if recovery.should_ask_user:
            return {"stop": True, "reason": "ask_user", "applied": False}

        if capability in READ_ONLY_CAPABILITIES and not recovery.should_abort:
            failed_step.status = StepStatus.READY
            return {"continue_failure": True}

        return {"stop": True, "reason": recovery.reason or "no_recovery", "applied": False}

    def _contextual_replan(
        self,
        *,
        goal: Goal,
        plan: Plan,
        failed_step: PlanStep,
        failure: FailureClass,
        observation: Observation,
        evaluation: Evaluation,
    ) -> bool:
        self.state = RuntimeState.REPLANNING
        goal.status = GoalStatus.REPLANNING
        context = self._build_replan_context(
            goal=goal,
            plan=plan,
            failed_step=failed_step,
            observation=observation,
            evaluation=evaluation,
        )

        candidate: Optional[CandidatePlan] = None
        if self.contextual_replan_enabled:
            candidate = self.replanner.replan(context)

        decision = self.policy_gate.approve(candidate, context) if candidate is not None else None
        if isinstance(decision, Reject) or decision is None:
            violations = decision.violations if isinstance(decision, Reject) else ["no_candidate"]
            self.traces.record(
                goal_id=goal.id,
                decision="contextual_replan",
                reason="policy_rejected" if isinstance(decision, Reject) else "no_candidate",
                tool=str((failed_step.required_capabilities or ["?"])[0]),
                result_summary=";".join(violations)[:200],
                next_action="fallback_or_abort",
                evaluation=evaluation.to_dict(),
                metadata={
                    "capability": (failed_step.required_capabilities or [""])[0],
                    "failure_class": failure.value,
                    "strategy_hint": (candidate.strategy_hint if candidate else ""),
                    "planner_source": (candidate.source if candidate else "none"),
                    "policy_approved": False,
                    "plan_version": plan.version,
                    "recovery": {"action": "reject", "violations": violations},
                },
            )
            # Fallback observe/wait (Batch 3 path) — still gated.
            fallback_plan = observation_replan(plan, failed_step, failure)
            if fallback_plan is None:
                return False
            fallback_candidate = CandidatePlan(
                plan=Plan(
                    goal_id=goal.id,
                    steps=[s for s in plan.steps if s.metadata.get("replan")],
                    version=plan.version,
                    metadata=dict(plan.metadata),
                ),
                replan_reason="policy_reject_fallback_observe_wait",
                strategy_hint="observe_wait",
                source="fallback_observe_wait",
            )
            # observation_replan already mutated plan; record and accept as fallback
            self.traces.record(
                goal_id=goal.id,
                decision="contextual_replan",
                reason="fallback_observe_wait",
                tool=str((failed_step.required_capabilities or ["?"])[0]),
                result_summary="fallback_after_reject",
                next_action="execute",
                evaluation=evaluation.to_dict(),
                metadata={
                    "capability": (failed_step.required_capabilities or [""])[0],
                    "failure_class": failure.value,
                    "strategy_hint": "observe_wait",
                    "planner_source": "fallback_observe_wait",
                    "policy_approved": True,
                    "plan_version": plan.version,
                    "recovery": {"action": "fallback"},
                },
            )
            self._recovery_history.append(
                {"strategy": "fallback_observe_wait", "failure_class": failure.value}
            )
            return True

        approved: ApprovedPlan = decision
        self._merge_approved_plan(plan, failed_step, approved)
        self.traces.record(
            goal_id=goal.id,
            decision="contextual_replan",
            reason=approved.candidate.replan_reason or "contextual_replan",
            tool=str((failed_step.required_capabilities or ["?"])[0]),
            result_summary=approved.candidate.strategy_hint,
            next_action="execute",
            evaluation=evaluation.to_dict(),
            metadata={
                "capability": (failed_step.required_capabilities or [""])[0],
                "failure_class": failure.value,
                "strategy_hint": approved.candidate.strategy_hint,
                "planner_source": approved.candidate.source,
                "policy_approved": True,
                "plan_version": plan.version,
                "recovery": {"action": "approve", "source": approved.candidate.source},
            },
        )
        self._recovery_history.append(
            {
                "strategy": approved.candidate.strategy_hint,
                "source": approved.candidate.source,
                "failure_class": failure.value,
            }
        )
        return True

    def _build_replan_context(
        self,
        *,
        goal: Goal,
        plan: Plan,
        failed_step: PlanStep,
        observation: Observation,
        evaluation: Evaluation,
    ) -> ReplanContext:
        available = list(self.capabilities.describe().get("registry_capabilities") or [])
        return ReplanContext(
            original_goal=goal,
            current_plan=plan,
            failed_step=failed_step,
            observation=observation,
            evaluation=evaluation,
            recovery_history=list(self._recovery_history),
            available_capabilities=available,
            policy_constraints=self.policy_constraints,
            budget_remaining={
                "iterations_remaining": max(0, self.budget.max_iterations - self.usage.iterations),
                "retries_remaining": max(0, self.budget.max_retries - self.usage.retries),
                "replans_remaining": max(0, self.budget.max_replans - self.usage.replans - 1),
            },
        )

    def _merge_approved_plan(self, plan: Plan, failed_step: PlanStep, approved: ApprovedPlan) -> None:
        failed_step.status = StepStatus.FAILED
        for step in plan.steps:
            if step.id == failed_step.id:
                continue
            if step.status not in {StepStatus.PENDING, StepStatus.READY}:
                continue
            step.status = StepStatus.SKIPPED
            step.metadata["skipped_reason"] = "replaced_by_contextual_replan"
        plan.steps.extend(list(approved.plan.steps))
        plan.version = max(plan.version + 1, int(approved.plan.version or plan.version + 1))
        plan.metadata["replanned"] = True
        plan.metadata["replan_reason"] = approved.candidate.replan_reason
        plan.metadata["strategy_hint"] = approved.candidate.strategy_hint
        plan.metadata["planner_source"] = approved.candidate.source

    def _persist_snapshot(
        self,
        goal: Goal,
        plan: Plan,
        *,
        goal_plan: Dict[str, Any],
        last_observation: Optional[Dict[str, Any]],
        last_evaluation: Optional[Dict[str, Any]],
    ) -> Optional[GoalSnapshot]:
        if self.goal_store is None:
            return None
        ttl = float((self.cfg.get("goal_persistence") or {}).get("ttl_s", 600)) if isinstance(self.cfg.get("goal_persistence"), dict) else 600.0
        now = time.time()
        # Sync runtime fields onto goal_plan for resume
        resume_plan = dict(goal_plan) if goal_plan else {}
        resume_plan["typed_goal"] = goal.to_dict()
        resume_plan["typed_plan"] = plan.to_dict()
        resume_plan["_runtime_budget_usage"] = self.usage.to_dict()
        resume_plan["_progress_signatures"] = self.progress.signatures()
        resume_plan["_zero_progress"] = self.progress.snapshot()[1]
        resume_plan["_recovery_history"] = list(self._recovery_history)
        # Rebuild actions from remaining ready steps for executor translation
        actions = []
        for step in plan.steps:
            if step.status not in {StepStatus.PENDING, StepStatus.READY}:
                continue
            action = dict(step.metadata.get("action") or {})
            cap = str(step.required_capabilities[0]) if step.required_capabilities else ""
            if cap and "capability" not in action:
                action["capability"] = cap
            if action:
                actions.append(action)
        if actions:
            resume_plan["actions"] = actions

        snap = GoalSnapshot(
            goal_id=goal.id,
            objective=goal.objective,
            status=goal.status,
            params={
                "behavior": resume_plan.get("behavior"),
                "dominant_need": resume_plan.get("dominant_need"),
                "recommended_goal": resume_plan.get("recommended_goal"),
                "intent": resume_plan.get("intent") or (goal.metadata or {}).get("intent"),
            },
            created_at=float(goal.created_at or now),
            updated_at=now,
            expires_at=now + ttl,
            current_plan=plan.to_dict(),
            goal_plan=resume_plan,
            last_observation=_summarize_observation(last_observation),
            last_evaluation=last_evaluation,
            recovery_attempts=list(self._recovery_history)[-8:],
            budget_usage=self.usage.to_dict(),
            progress_signatures=self.progress.signatures(),
            metadata={"state": self.state.value},
        )
        # Never persist sticky REPLANNING without remaining work.
        if snap.status == GoalStatus.REPLANNING and not snap.has_executable_work():
            snap.status = GoalStatus.FAILED
            goal.status = GoalStatus.FAILED
        elif snap.status == GoalStatus.REPLANNING and snap.has_executable_work():
            snap.status = GoalStatus.WAITING
            goal.status = GoalStatus.WAITING

        existing = self.goal_store.get(goal.id)
        if existing is None:
            self.goal_store.create(snap)
        else:
            snap.created_at = existing.created_at
            snap.expires_at = existing.expires_at or snap.expires_at
            self.goal_store.save(snap)
        if snap.status in {
            GoalStatus.COMPLETED,
            GoalStatus.FAILED,
            GoalStatus.CANCELLED,
            GoalStatus.EXPIRED,
            GoalStatus.SUPERSEDED,
        }:
            self.goal_store.complete(snap.goal_id, snap.status)
            self.goal_store.prune_terminals()
        return snap

    def _trace(
        self,
        goal_id: str,
        plan_step: PlanStep,
        capability: str,
        evaluation: Evaluation,
        next_action: str,
        raw_result: Dict[str, Any],
    ) -> None:
        self.traces.record(
            goal_id=goal_id,
            decision="execute_capability" if evaluation.execution_success else "capability_failed",
            reason=evaluation.reason,
            tool=capability,
            result_summary=str(raw_result.get("reason") or raw_result.get("error") or "ok")[:200],
            next_action=next_action,
            evaluation=evaluation.to_dict(),
            metadata={"capability": capability, "step_objective": plan_step.objective},
        )


def _summarize_observation(obs: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(obs, dict):
        return None
    result = obs.get("result")
    reason = ""
    if isinstance(result, dict):
        reason = str(result.get("reason") or result.get("error") or "")[:200]
    else:
        reason = str(result or "")[:200]
    return {
        "source": obs.get("source"),
        "success": obs.get("success"),
        "action_id": obs.get("action_id"),
        "reason": reason,
        "metadata": {
            k: v
            for k, v in dict(obs.get("metadata") or {}).items()
            if k in {"capability", "failure_class", "recovery"}
        },
    }
