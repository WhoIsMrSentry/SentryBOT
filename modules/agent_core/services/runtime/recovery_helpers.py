"""Shared contextual replanning and plan-merge helpers for AgentRuntime and CompanionExecutionLoop."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .capability_index import CapabilityIndex
from .contextual_replanner import ContextualReplanner
from .decision_trace import DecisionTraceStore
from .plan_policy_gate import ApprovedPlan, PlanPolicyGate, Reject
from .schemas import (
    CandidatePlan,
    Evaluation,
    FailureClass,
    Goal,
    Observation,
    Plan,
    PlanStep,
    PolicyConstraints,
    ReplanContext,
    RuntimeBudgetUsage,
    Budget,
    StepStatus,
)


def build_replan_context(
    *,
    goal: Goal,
    plan: Plan,
    failed_step: PlanStep,
    observation: Observation,
    evaluation: Evaluation,
    capabilities: CapabilityIndex,
    policy_constraints: PolicyConstraints,
    budget: Budget,
    usage: RuntimeBudgetUsage,
    recovery_history: Sequence[Dict[str, Any]] = (),
) -> ReplanContext:
    """Build deterministic ReplanContext from current execution state."""
    available = list(capabilities.describe().get("registry_capabilities") or [])
    return ReplanContext(
        original_goal=goal,
        current_plan=plan,
        failed_step=failed_step,
        observation=observation,
        evaluation=evaluation,
        recovery_history=list(recovery_history),
        available_capabilities=available,
        policy_constraints=policy_constraints,
        budget_remaining={
            "iterations_remaining": max(0, int(budget.max_iterations) - int(usage.iterations)),
            "retries_remaining": max(0, int(budget.max_retries) - int(usage.retries)),
            "replans_remaining": max(0, int(budget.max_replans) - int(usage.replans)),
        },
    )


def merge_approved_plan(
    plan: Plan,
    failed_step: Optional[PlanStep],
    approved: ApprovedPlan,
) -> None:
    """Apply an ApprovedPlan onto ``plan``, skipping superseded remaining steps."""
    if failed_step is not None:
        failed_step.status = StepStatus.FAILED
    for step in plan.steps:
        if failed_step is not None and step.id == failed_step.id:
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


def run_contextual_replan(
    *,
    replanner: ContextualReplanner,
    policy_gate: PlanPolicyGate,
    traces: DecisionTraceStore,
    goal: Goal,
    plan: Plan,
    failed_step: PlanStep,
    failure: FailureClass,
    observation: Observation,
    evaluation: Evaluation,
    context: ReplanContext,
) -> Optional[ApprovedPlan]:
    """Generate a candidate replan, gate it with PlanPolicyGate, and record traces."""
    candidate: Optional[CandidatePlan] = replanner.replan(context)
    decision = policy_gate.approve(candidate, context) if candidate is not None else None
    failed_cap = str((failed_step.required_capabilities or ["?"])[0])

    if isinstance(decision, Reject) or decision is None:
        violations: List[str] = list(decision.violations) if isinstance(decision, Reject) else ["no_candidate"]
        traces.record(
            goal_id=goal.id,
            decision="contextual_replan",
            reason="policy_rejected" if isinstance(decision, Reject) else "no_candidate",
            tool=failed_cap,
            result_summary=";".join(violations)[:200],
            next_action="fallback_or_abort",
            evaluation=evaluation.to_dict(),
            metadata={
                "capability": (failed_step.required_capabilities or [""])[0],
                "failure_class": failure.value,
                "strategy_hint": candidate.strategy_hint if candidate else "",
                "planner_source": candidate.source if candidate else "none",
                "policy_approved": False,
                "plan_version": plan.version,
                "recovery": {"action": "reject", "violations": violations},
            },
        )
        return None

    approved: ApprovedPlan = decision
    merge_approved_plan(plan, failed_step, approved)
    traces.record(
        goal_id=goal.id,
        decision="contextual_replan",
        reason=approved.candidate.replan_reason or "contextual_replan",
        tool=failed_cap,
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
    return approved


__all__ = ["build_replan_context", "merge_approved_plan", "run_contextual_replan"]
