"""Observation-contextual replanning — proposes CandidatePlan, never executes."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from .capability_index import CapabilityIndex
from .schemas import (
    CandidatePlan,
    FailureClass,
    Plan,
    PlanStep,
    ReplanContext,
    StepStatus,
)

LLMAssistFn = Callable[[ReplanContext], Optional[CandidatePlan]]

NAVIGATION_ALTERNATES: Dict[str, List[str]] = {
    "navigation.rest_corner": ["navigation.goal"],
    "navigation.goal": ["navigation.rest_corner"],
}

VISION_ALTERNATES: Dict[str, List[str]] = {
    "vision.cheap": ["vision.semantic", "memory.observe"],
    "vision.semantic": ["vision.cheap", "memory.observe"],
}

PERCEPTION_GATHER: List[str] = ["vision.cheap", "memory.observe"]


class ContextualReplanner:
    """Rules-first contextual planner with optional mocked LLM assist hook."""

    def __init__(
        self,
        *,
        capabilities: Optional[CapabilityIndex] = None,
        cfg: Optional[Dict[str, Any]] = None,
        llm_assist_fn: Optional[LLMAssistFn] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.capabilities = capabilities if capabilities is not None else CapabilityIndex.from_robot_registry()
        self.llm_assist = bool(raw.get("llm_assist", False))
        self.fallback_observe_wait = bool(raw.get("fallback_observe_wait", True))
        self.max_candidate_steps = max(1, int(raw.get("max_candidate_steps", 4)))
        self.llm_assist_fn = llm_assist_fn

    def replan(self, context: ReplanContext) -> CandidatePlan:
        # Rules-first even when llm_assist is enabled — LLM is an optional fill-in.
        rules = self._rules_candidate(context)
        if rules is not None:
            return rules

        if self.llm_assist and self.llm_assist_fn is not None:
            try:
                assisted = self.llm_assist_fn(context)
            except Exception:
                assisted = None
            if assisted is not None and isinstance(assisted.plan, Plan) and assisted.plan.steps:
                assisted.source = "llm_assisted"
                assisted.plan = self._trim(assisted.plan)
                return assisted

        return self._fallback_observe_wait(context)

    def _rules_candidate(self, context: ReplanContext) -> Optional[CandidatePlan]:
        failed_cap = self._failed_capability(context)
        reason = self._observation_reason(context)
        failure = context.evaluation.failure_class

        if failed_cap.startswith("navigation.") and self._looks_blocked(reason, failure):
            return self._navigation_obstacle(context, failed_cap)

        if failed_cap.startswith("vision.") and failure in {
            FailureClass.TOOL_UNAVAILABLE,
            FailureClass.TEMPORARY,
            FailureClass.UNEXPECTED_RESULT,
        }:
            return self._vision_unavailable(context, failed_cap)

        if failed_cap.startswith("perception.") and failure in {
            FailureClass.INSUFFICIENT_CONTEXT,
            FailureClass.UNEXPECTED_RESULT,
            FailureClass.INVALID_PLAN,
        }:
            return self._perception_gather(context, failed_cap)

        if failure == FailureClass.TEMPORARY and failed_cap.startswith(("vision.", "memory.", "scheduler.")):
            return self._temporary_observe_retry(context, failed_cap)

        return None

    def _navigation_obstacle(self, context: ReplanContext, failed_cap: str) -> CandidatePlan:
        available = set(context.available_capabilities) or set(self._enabled_caps())
        alts = [
            c
            for c in NAVIGATION_ALTERNATES.get(failed_cap, ["navigation.goal", "navigation.rest_corner"])
            if c != failed_cap and c in available and self.capabilities.is_capability_enabled(c)
        ]
        steps: List[PlanStep] = [
            self._step(
                "Observe after navigation block",
                "vision.cheap",
                {"type": "vision", "mode": "cheap", "reason": "nav_obstacle_replan"},
            )
        ]
        if alts:
            alt = alts[0]
            policy = alt.split(".", 1)[-1]
            steps.append(
                self._step(
                    f"Alternate navigation via {alt}",
                    alt,
                    {"type": "navigation", "policy": policy, "name": policy, "risk": "low", "reason": "alternate_route"},
                )
            )
            residual = self._residual_intent_steps(context, skip_prefixes=("navigation.",))
            steps.extend(residual)
            hint = "observe_then_reroute"
            reason = f"navigation_obstacle:{failed_cap}->observe+{alt}+residual"
            source = "rules"
        else:
            steps.append(
                self._step(
                    "Wait after blocked navigation",
                    "scheduler.wait",
                    {"type": "wait", "label": "nav_blocked_wait"},
                )
            )
            hint = "observe_wait_no_alternate"
            reason = f"navigation_obstacle:{failed_cap}->observe+wait"
            source = "fallback_observe_wait"

        plan = self._build_plan(context, steps)
        return CandidatePlan(plan=plan, replan_reason=reason, strategy_hint=hint, source=source)

    def _vision_unavailable(self, context: ReplanContext, failed_cap: str) -> Optional[CandidatePlan]:
        available = set(context.available_capabilities) or set(self._enabled_caps())
        alts = [
            c
            for c in VISION_ALTERNATES.get(failed_cap, ["vision.semantic", "memory.observe"])
            if c != failed_cap and c in available and self.capabilities.is_capability_enabled(c)
        ]
        if not alts:
            return None
        alt = alts[0]
        steps = [
            self._step(
                f"Alternate vision via {alt}",
                alt,
                {"type": "vision" if alt.startswith("vision.") else "memory", "mode": alt.split(".")[-1], "reason": "vision_unavailable"},
            )
        ]
        residual = self._residual_intent_steps(context, skip_prefixes=("vision.",))
        steps.extend(residual)
        plan = self._build_plan(context, steps)
        return CandidatePlan(
            plan=plan,
            replan_reason=f"vision_unavailable:{failed_cap}->{alt}",
            strategy_hint="switch_vision_capability",
            source="rules",
        )

    def _perception_gather(self, context: ReplanContext, failed_cap: str) -> CandidatePlan:
        available = set(context.available_capabilities) or set(self._enabled_caps())
        gather = [
            c
            for c in PERCEPTION_GATHER
            if c in available and self.capabilities.is_capability_enabled(c)
        ]
        cap = gather[0] if gather else "vision.cheap"
        steps = [
            self._step(
                "Gather context after perception miss",
                cap,
                {"type": "vision" if cap.startswith("vision.") else "memory", "mode": "cheap", "reason": "perception_gather"},
            )
        ]
        # Re-queue a soft reevaluation wait then residual intent (not pure wait-only).
        residual = self._residual_intent_steps(context, skip_prefixes=("perception.",))
        if residual:
            steps.extend(residual)
        else:
            steps.append(
                self._step(
                    "Brief wait before reevaluate",
                    "scheduler.wait",
                    {"type": "wait", "label": "perception_reevaluate"},
                )
            )
        plan = self._build_plan(context, steps)
        return CandidatePlan(
            plan=plan,
            replan_reason=f"perception_insufficient:{failed_cap}->gather",
            strategy_hint="gather_context_continue",
            source="rules",
        )

    def _temporary_observe_retry(self, context: ReplanContext, failed_cap: str) -> CandidatePlan:
        steps = [
            self._step(
                "Observe before modified retry",
                "vision.cheap" if self.capabilities.is_capability_enabled("vision.cheap") else "memory.observe",
                {"type": "vision", "mode": "cheap", "reason": "temporary_observe"},
            ),
            self._step(
                f"Retry {failed_cap} after observe",
                failed_cap,
                dict((context.failed_step.metadata or {}).get("action") or {"capability": failed_cap}),
            ),
        ]
        plan = self._build_plan(context, steps)
        return CandidatePlan(
            plan=plan,
            replan_reason=f"temporary:{failed_cap}->observe_retry",
            strategy_hint="observe_then_retry",
            source="rules",
        )

    def _fallback_observe_wait(self, context: ReplanContext) -> CandidatePlan:
        steps = [
            self._step(
                "Observe after failure",
                "vision.cheap",
                {"type": "vision", "mode": "cheap", "reason": "fallback_replan_observe"},
            ),
            self._step(
                "Wait after replan",
                "scheduler.wait",
                {"type": "wait", "label": "fallback_replan_wait"},
            ),
        ]
        plan = self._build_plan(context, steps)
        return CandidatePlan(
            plan=plan,
            replan_reason="fallback_observe_wait",
            strategy_hint="observe_wait",
            source="fallback_observe_wait",
            metadata={"fallback": True},
        )

    def _residual_intent_steps(
        self,
        context: ReplanContext,
        *,
        skip_prefixes: Sequence[str],
    ) -> List[PlanStep]:
        residual: List[PlanStep] = []
        for step in context.current_plan.steps:
            if step.id == context.failed_step.id:
                continue
            if step.status not in {StepStatus.PENDING, StepStatus.READY}:
                continue
            cap = str(step.required_capabilities[0]) if step.required_capabilities else ""
            if any(cap.startswith(prefix) for prefix in skip_prefixes):
                continue
            if cap.startswith(("navigation.", "motion.")) and any(
                p.startswith("navigation.") for p in skip_prefixes
            ):
                # Keep pose/expression/speech residuals; drop dependent motion after nav block
                # unless it's pose (preserve inspect/pose intent).
                if not cap.startswith("pose."):
                    continue
            residual.append(
                PlanStep(
                    objective=step.objective,
                    required_capabilities=list(step.required_capabilities),
                    preferred_tools=list(step.preferred_tools),
                    status=StepStatus.READY,
                    success_criteria=list(step.success_criteria),
                    fallback_strategy=step.fallback_strategy,
                    metadata={**dict(step.metadata), "residual_intent": True},
                )
            )
            if len(residual) >= self.max_candidate_steps:
                break
        return residual

    def _build_plan(self, context: ReplanContext, steps: List[PlanStep]) -> Plan:
        trimmed = self._trim_steps(steps)
        prev: Optional[str] = None
        for step in trimmed:
            step.dependencies = [prev] if prev else []
            step.status = StepStatus.READY
            prev = step.id
        return Plan(
            goal_id=context.original_goal.id,
            steps=trimmed,
            version=int(context.current_plan.version) + 1,
            metadata={
                **dict(context.current_plan.metadata),
                "replanned": True,
                "replan_from_step": context.failed_step.id,
            },
        )

    def _trim(self, plan: Plan) -> Plan:
        plan.steps = self._trim_steps(list(plan.steps))
        return plan

    def _trim_steps(self, steps: List[PlanStep]) -> List[PlanStep]:
        return list(steps)[: self.max_candidate_steps]

    def _step(self, objective: str, capability: str, action: Dict[str, Any]) -> PlanStep:
        return PlanStep(
            objective=objective,
            required_capabilities=[capability],
            status=StepStatus.READY,
            metadata={"action": action, "risk": str(action.get("risk") or "none"), "replan": True},
        )

    def _enabled_caps(self) -> List[str]:
        described = self.capabilities.describe()
        return list(described.get("registry_capabilities") or [])

    @staticmethod
    def _failed_capability(context: ReplanContext) -> str:
        step = context.failed_step
        if step.required_capabilities:
            return str(step.required_capabilities[0])
        meta = step.metadata or {}
        action = meta.get("action") if isinstance(meta.get("action"), dict) else {}
        return str(action.get("capability") or meta.get("capability") or "")

    @staticmethod
    def _observation_reason(context: ReplanContext) -> str:
        result = context.observation.result
        if isinstance(result, dict):
            return str(result.get("reason") or result.get("error") or "").lower()
        return str(result or context.evaluation.reason or "").lower()

    @staticmethod
    def _looks_blocked(reason: str, failure: FailureClass) -> bool:
        tokens = ("obstacle", "blocked", "path", "collision", "occupied", "handler_failed")
        if any(token in reason for token in tokens):
            return True
        return failure in {
            FailureClass.TEMPORARY,
            FailureClass.TOOL_UNAVAILABLE,
            FailureClass.VALIDATION,
            FailureClass.UNEXPECTED_RESULT,
            FailureClass.INVALID_PLAN,
        }


__all__ = ["ContextualReplanner", "LLMAssistFn", "NAVIGATION_ALTERNATES"]
