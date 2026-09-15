"""Bounded Observe → Decide → Act → Evaluate → Adapt runtime.

This adapter does not replace AutonomyBrain or AgentOrchestrator.
It provides a typed cognitive loop that can wrap tool execution for
multi-step goals with budgets, recovery, and decision traces.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from .capability_index import CapabilityIndex
from .decision_trace import DecisionTraceStore
from .progress_tracker import ProgressTracker
from .recovery import FailureClassifier, RecoveryManager
from .schemas import (
    AgentActionKind,
    Budget,
    CandidateAction,
    Evaluation,
    FailureClass,
    Goal,
    GoalStatus,
    Observation,
    Plan,
    PlanStep,
    RuntimeBudgetUsage,
    RuntimeState,
    StepStatus,
)

logger = logging.getLogger("agent.runtime")

ToolExecutor = Callable[[str, Dict[str, Any]], Any]
DecisionFn = Callable[["AgentRuntime", Goal, Optional[Plan], Optional[PlanStep]], CandidateAction]
EvaluateFn = Callable[[Goal, CandidateAction, Observation], Evaluation]


class AgentRuntime:
    """Coordinates one bounded goal-solving session."""

    def __init__(
        self,
        *,
        tool_executor: Optional[ToolExecutor] = None,
        capability_index: Optional[CapabilityIndex] = None,
        budget: Optional[Budget] = None,
        decide_fn: Optional[DecisionFn] = None,
        evaluate_fn: Optional[EvaluateFn] = None,
        available_tools: Optional[Sequence[str]] = None,
    ) -> None:
        self.tool_executor = tool_executor
        self.capabilities = capability_index or CapabilityIndex.from_robot_registry()
        self.budget = budget or Budget()
        self.usage = RuntimeBudgetUsage()
        self.classifier = FailureClassifier()
        self.recovery = RecoveryManager()
        self.progress = ProgressTracker()
        self.traces = DecisionTraceStore()
        self.decide_fn = decide_fn or self._default_decide
        self.evaluate_fn = evaluate_fn or self._default_evaluate
        self.available_tools = list(available_tools or [])
        self.state = RuntimeState.IDLE
        self.goal: Optional[Goal] = None
        self.plan: Optional[Plan] = None
        self.observations: List[Observation] = []
        self.last_evaluation: Optional[Evaluation] = None
        self.last_recovery = None

    def create_simple_plan(
        self,
        goal: Goal,
        steps: Sequence[Dict[str, Any]],
    ) -> Plan:
        plan_steps = [
            PlanStep.from_dict(step if isinstance(step, dict) else {"objective": str(step)})
            for step in steps
        ]
        for step in plan_steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.READY
        return Plan(goal_id=goal.id, steps=plan_steps)

    def run(
        self,
        goal: Goal,
        plan: Optional[Plan] = None,
        *,
        reset_budget: bool = True,
    ) -> Dict[str, Any]:
        if reset_budget:
            self.usage = RuntimeBudgetUsage()
            self.progress.reset()
        self.goal = goal
        self.plan = plan
        goal.status = GoalStatus.ACTIVE
        self.state = RuntimeState.OBSERVING
        self.observations = []
        self.last_evaluation = None
        self.last_recovery = None

        stop_reason = ""
        while True:
            exceeded = self.usage.exceeded(self.budget)
            if exceeded:
                self.state = RuntimeState.BUDGET_EXCEEDED
                stop_reason = exceeded
                goal.status = GoalStatus.FAILED
                break

            self.usage.iterations += 1
            step = self.plan.next_ready_step() if self.plan else None

            self.state = RuntimeState.DECIDING
            candidate = self.decide_fn(self, goal, self.plan, step)
            if candidate.action == AgentActionKind.COMPLETE_GOAL:
                self.state = RuntimeState.COMPLETED
                goal.status = GoalStatus.COMPLETED
                self.traces.record(
                    goal_id=goal.id,
                    decision="complete_goal",
                    reason=candidate.rationale or "goal_complete",
                    iteration=self.usage.iterations,
                    next_action="done",
                )
                stop_reason = "completed"
                break
            if candidate.action == AgentActionKind.ABORT:
                self.state = RuntimeState.FAILED
                goal.status = GoalStatus.FAILED
                self.traces.record(
                    goal_id=goal.id,
                    decision="abort",
                    reason=candidate.rationale or "aborted",
                    iteration=self.usage.iterations,
                )
                stop_reason = "aborted"
                break
            if candidate.action == AgentActionKind.WAIT:
                self.state = RuntimeState.WAITING_FOR_INPUT
                goal.status = GoalStatus.WAITING
                stop_reason = "waiting"
                break
            if candidate.action == AgentActionKind.REQUEST_PERMISSION:
                self.state = RuntimeState.WAITING_FOR_PERMISSION
                goal.status = GoalStatus.WAITING
                stop_reason = "permission_required"
                break
            if candidate.action == AgentActionKind.REQUEST_INFORMATION:
                self.state = RuntimeState.WAITING_FOR_INPUT
                goal.status = GoalStatus.WAITING
                stop_reason = "need_information"
                break

            signature = self._action_signature(candidate)
            observation = self._execute_candidate(candidate, step)
            self.observations.append(observation)

            self.state = RuntimeState.EVALUATING
            evaluation = self.evaluate_fn(goal, candidate, observation)
            self.last_evaluation = evaluation

            stall = self.progress.record(signature, progressed=bool(observation.success))
            if stall:
                self.state = RuntimeState.FAILED
                goal.status = GoalStatus.FAILED
                stop_reason = stall
                self.traces.record(
                    goal_id=goal.id,
                    decision="stop",
                    reason=stall,
                    tool=candidate.tool_name,
                    iteration=self.usage.iterations,
                    evaluation=evaluation.to_dict(),
                )
                break

            self.traces.record(
                goal_id=goal.id,
                decision=candidate.action.value,
                reason=candidate.rationale or evaluation.reason,
                tool=candidate.tool_name,
                result_summary=str(observation.result)[:200],
                next_action="recover" if not evaluation.execution_success else "continue",
                evaluation=evaluation.to_dict(),
                iteration=self.usage.iterations,
            )

            if step is not None and self.plan is not None:
                if evaluation.execution_success:
                    step.status = StepStatus.SUCCEEDED
                else:
                    step.status = StepStatus.FAILED

            if evaluation.goal_success:
                self.state = RuntimeState.COMPLETED
                goal.status = GoalStatus.COMPLETED
                stop_reason = "goal_success"
                break

            if not evaluation.execution_success or evaluation.should_replan:
                recovered = self._handle_failure(goal, candidate, evaluation, step)
                if recovered.get("stop"):
                    stop_reason = str(recovered.get("reason") or "recovery_stop")
                    break
                continue

            if self.plan and self.plan.next_ready_step() is None:
                # All steps done but goal_success false → complete if executions ok
                if all(
                    s.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
                    for s in self.plan.steps
                ):
                    self.state = RuntimeState.COMPLETED
                    goal.status = GoalStatus.COMPLETED
                    stop_reason = "plan_exhausted_success"
                    break
                self.state = RuntimeState.FAILED
                goal.status = GoalStatus.FAILED
                stop_reason = "plan_exhausted_without_success"
                break

        return self.snapshot(stop_reason=stop_reason)

    def snapshot(self, stop_reason: str = "") -> Dict[str, Any]:
        return {
            "ok": self.state in {RuntimeState.COMPLETED, RuntimeState.WAITING_FOR_INPUT, RuntimeState.WAITING_FOR_PERMISSION},
            "state": self.state.value,
            "stop_reason": stop_reason,
            "goal": self.goal.to_dict() if self.goal else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "budget": self.budget.to_dict(),
            "usage": {
                "iterations": self.usage.iterations,
                "tool_calls": self.usage.tool_calls,
                "retries": self.usage.retries,
                "replans": self.usage.replans,
            },
            "observations": [o.to_dict() for o in self.observations[-10:]],
            "evaluation": self.last_evaluation.to_dict() if self.last_evaluation else None,
            "recovery": self.last_recovery.to_dict() if self.last_recovery else None,
            "traces": self.traces.recent(10),
            "capability_gaps": self.capabilities.capability_gap(
                self._required_capabilities(),
                available_tools=self.available_tools or None,
            ),
        }

    def _required_capabilities(self) -> List[str]:
        if not self.plan:
            return []
        caps: List[str] = []
        for step in self.plan.steps:
            if step.status in {StepStatus.PENDING, StepStatus.READY, StepStatus.RUNNING, StepStatus.FAILED}:
                caps.extend(step.required_capabilities)
        return caps

    def _execute_candidate(
        self,
        candidate: CandidateAction,
        step: Optional[PlanStep],
    ) -> Observation:
        self.state = RuntimeState.EXECUTING
        if step is not None:
            step.status = StepStatus.RUNNING

        if candidate.action == AgentActionKind.RESPOND:
            return Observation(
                source="runtime.respond",
                result=candidate.expected_outcome or candidate.rationale,
                success=True,
                action_id=candidate.step_id,
                metadata={"kind": "respond"},
            )

        if candidate.action != AgentActionKind.USE_TOOL:
            return Observation(
                source="runtime.noop",
                result=candidate.action.value,
                success=True,
                action_id=candidate.step_id,
            )

        tool_name = str(candidate.tool_name or "").strip()
        if not tool_name:
            gaps = self.capabilities.capability_gap(
                [candidate.capability] if candidate.capability else [],
                available_tools=self.available_tools or None,
            )
            return Observation(
                source="runtime.tool",
                result={"error": "tool_not_selected", "gaps": gaps},
                success=False,
                confidence=0.0,
                action_id=candidate.step_id,
                metadata={"failure_class": FailureClass.TOOL_UNAVAILABLE.value},
            )

        if self.tool_executor is None:
            return Observation(
                source="runtime.tool",
                result=f"Error: no tool executor for {tool_name}",
                success=False,
                metadata={"failure_class": FailureClass.TOOL_UNAVAILABLE.value},
            )

        self.usage.tool_calls += 1
        try:
            result = self.tool_executor(tool_name, dict(candidate.tool_args or {}))
            success = not _looks_like_error(result)
            failure = self.classifier.classify(success=success, result=result)
            return Observation(
                source=f"tool.{tool_name}",
                result=result,
                success=success,
                confidence=0.9 if success else 0.2,
                action_id=candidate.step_id,
                metadata={"failure_class": failure.value, "tool": tool_name},
            )
        except Exception as exc:
            logger.warning("Tool execution failed: %s", exc)
            failure = self.classifier.classify(success=False, error=str(exc))
            return Observation(
                source=f"tool.{tool_name}",
                result=str(exc),
                success=False,
                confidence=0.0,
                action_id=candidate.step_id,
                metadata={"failure_class": failure.value, "tool": tool_name},
            )

    def _handle_failure(
        self,
        goal: Goal,
        candidate: CandidateAction,
        evaluation: Evaluation,
        step: Optional[PlanStep],
    ) -> Dict[str, Any]:
        self.state = RuntimeState.RECOVERING
        failure = evaluation.failure_class
        if failure == FailureClass.NONE:
            raw = str((evaluation.metadata or {}).get("failure_class") or FailureClass.UNKNOWN.value)
            try:
                failure = FailureClass(raw)
            except ValueError:
                failure = FailureClass.UNKNOWN

        alts: List[str] = []
        if candidate.capability:
            alts = [
                t
                for t in self.capabilities.tools_for_capability(candidate.capability)
                if t != candidate.tool_name
            ]
        decision = self.recovery.decide(
            failure,
            attempt=self.usage.retries,
            max_retries=self.budget.max_retries,
            alternate_tools=alts,
            has_plan=self.plan is not None,
        )
        self.last_recovery = decision

        if decision.should_retry:
            self.usage.retries += 1
            if step is not None:
                step.status = StepStatus.READY
            return {"stop": False, "reason": "retry"}

        if decision.should_switch_tool and decision.alternate_tool:
            self.usage.retries += 1
            if step is not None:
                step.status = StepStatus.READY
                step.preferred_tools = [decision.alternate_tool] + list(step.preferred_tools)
            return {"stop": False, "reason": "switch_tool"}

        if decision.should_replan and self.plan is not None:
            self.usage.replans += 1
            self.state = RuntimeState.REPLANNING
            if self.usage.replans > self.budget.max_replans:
                goal.status = GoalStatus.FAILED
                self.state = RuntimeState.FAILED
                return {"stop": True, "reason": "max_replans"}
            # Soft replan: reopen failed step as ready once
            if step is not None:
                step.status = StepStatus.READY
                step.fallback_strategy = decision.strategy
            return {"stop": False, "reason": "replan"}

        if decision.should_ask_user:
            goal.status = GoalStatus.WAITING
            self.state = RuntimeState.WAITING_FOR_INPUT
            return {"stop": True, "reason": "ask_user"}

        if decision.should_abort:
            goal.status = GoalStatus.FAILED
            self.state = RuntimeState.FAILED
            return {"stop": True, "reason": decision.reason or "abort"}

        goal.status = GoalStatus.FAILED
        self.state = RuntimeState.FAILED
        return {"stop": True, "reason": decision.reason or "unhandled_failure"}

    def _default_decide(
        self,
        runtime: "AgentRuntime",
        goal: Goal,
        plan: Optional[Plan],
        step: Optional[PlanStep],
    ) -> CandidateAction:
        if step is None:
            return CandidateAction(
                action=AgentActionKind.COMPLETE_GOAL,
                rationale="no_pending_steps",
                confidence=0.8,
            )

        tool_name = None
        if step.preferred_tools:
            tool_name = step.preferred_tools[0]
        elif step.required_capabilities:
            selected = self.capabilities.select_tools(
                step.required_capabilities,
                available_tools=self.available_tools or None,
            )
            tool_name = selected[0] if selected else None
            if not tool_name:
                gaps = self.capabilities.capability_gap(
                    step.required_capabilities,
                    available_tools=self.available_tools or None,
                )
                return CandidateAction(
                    action=AgentActionKind.ABORT,
                    rationale="capability_gap",
                    confidence=0.9,
                    risk="none",
                    metadata={"gaps": gaps},
                )

        if not tool_name:
            return CandidateAction(
                action=AgentActionKind.RESPOND,
                rationale=step.objective,
                expected_outcome=step.objective,
                confidence=0.4,
                step_id=step.id,
            )

        return CandidateAction(
            action=AgentActionKind.USE_TOOL,
            rationale=step.objective,
            expected_outcome="tool_result_satisfies_step",
            confidence=0.7,
            tool_name=tool_name,
            tool_args=dict(step.metadata.get("tool_args") or {}),
            capability=(step.required_capabilities[0] if step.required_capabilities else None),
            step_id=step.id,
            risk=str(step.metadata.get("risk") or "low"),
        )

    def _default_evaluate(
        self,
        goal: Goal,
        candidate: CandidateAction,
        observation: Observation,
    ) -> Evaluation:
        failure = self.classifier.classify(
            success=observation.success,
            result=observation.result,
            metadata=observation.metadata,
        )
        goal_success = False
        if observation.success and self.plan is not None:
            pending = [
                s
                for s in self.plan.steps
                if s.status not in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
                and s.id != candidate.step_id
            ]
            # Current step counted as success when observation.success
            goal_success = len(pending) == 0 and (
                not goal.success_criteria
                or _criteria_met(goal.success_criteria, observation)
            )
        elif observation.success and not self.plan:
            goal_success = _criteria_met(goal.success_criteria, observation) if goal.success_criteria else True

        return Evaluation(
            execution_success=bool(observation.success),
            goal_success=bool(goal_success),
            needs_more_information=failure == FailureClass.INSUFFICIENT_CONTEXT,
            should_replan=failure in {FailureClass.INVALID_PLAN, FailureClass.UNEXPECTED_RESULT},
            confidence=float(observation.confidence),
            reason="ok" if observation.success else failure.value,
            failure_class=failure,
        )

    @staticmethod
    def _action_signature(candidate: CandidateAction) -> str:
        return f"{candidate.action.value}:{candidate.tool_name or ''}:{sorted((candidate.tool_args or {}).items())}"


def _looks_like_error(result: Any) -> bool:
    text = str(result or "").strip().lower()
    if not text:
        return False
    return text.startswith("error") or "error executing" in text or text.startswith("traceback")


def _criteria_met(criteria: Sequence[str], observation: Observation) -> bool:
    if not criteria:
        return True
    blob = str(observation.result or "").lower()
    return all(str(c).lower() in blob for c in criteria)
