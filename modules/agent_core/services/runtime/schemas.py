"""Typed cognitive-loop schemas for AgentRuntime.

These are additive structures. Existing dict-based companion plans and
AgentOrchestrator turns remain valid; the runtime converts to/from dicts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    WAITING = "waiting"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class RuntimeState(str, Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    PLANNING = "planning"
    DECIDING = "deciding"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    RECOVERING = "recovering"
    REPLANNING = "replanning"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"


class FailureClass(str, Enum):
    NONE = "none"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    PERMISSION = "permission"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    TOOL_UNAVAILABLE = "tool_unavailable"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    INVALID_PLAN = "invalid_plan"
    UNEXPECTED_RESULT = "unexpected_result"
    UNSAFE_ACTION = "unsafe_action"
    BUDGET_EXCEEDED = "budget_exceeded"
    NO_PROGRESS = "no_progress"
    UNKNOWN = "unknown"


class AgentActionKind(str, Enum):
    RESPOND = "respond"
    USE_TOOL = "use_tool"
    CREATE_TASK = "create_task"
    UPDATE_PLAN = "update_plan"
    REQUEST_INFORMATION = "request_information"
    REQUEST_PERMISSION = "request_permission"
    WAIT = "wait"
    RETRY = "retry"
    ABORT = "abort"
    COMPLETE_GOAL = "complete_goal"
    RECOVER = "recover"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Goal:
    objective: str
    id: str = field(default_factory=lambda: _new_id("goal"))
    status: GoalStatus = GoalStatus.PENDING
    priority: float = 0.5
    constraints: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    parent_goal_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Goal":
        status = raw.get("status", GoalStatus.PENDING)
        if isinstance(status, str):
            status = GoalStatus(status)
        return cls(
            id=str(raw.get("id") or _new_id("goal")),
            objective=str(raw.get("objective") or ""),
            status=status,
            priority=float(raw.get("priority", 0.5)),
            constraints=list(raw.get("constraints") or []),
            success_criteria=list(raw.get("success_criteria") or []),
            created_at=float(raw.get("created_at") or time.time()),
            deadline=raw.get("deadline"),
            parent_goal_id=raw.get("parent_goal_id"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class PlanStep:
    objective: str
    id: str = field(default_factory=lambda: _new_id("step"))
    required_capabilities: List[str] = field(default_factory=list)
    preferred_tools: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    success_criteria: List[str] = field(default_factory=list)
    fallback_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PlanStep":
        status = raw.get("status", StepStatus.PENDING)
        if isinstance(status, str):
            status = StepStatus(status)
        return cls(
            id=str(raw.get("id") or _new_id("step")),
            objective=str(raw.get("objective") or ""),
            required_capabilities=list(raw.get("required_capabilities") or []),
            preferred_tools=list(raw.get("preferred_tools") or []),
            dependencies=list(raw.get("dependencies") or []),
            status=status,
            success_criteria=list(raw.get("success_criteria") or []),
            fallback_strategy=raw.get("fallback_strategy"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class Plan:
    goal_id: str
    steps: List[PlanStep] = field(default_factory=list)
    id: str = field(default_factory=lambda: _new_id("plan"))
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "version": self.version,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Plan":
        steps_raw = raw.get("steps") or []
        return cls(
            id=str(raw.get("id") or _new_id("plan")),
            goal_id=str(raw.get("goal_id") or ""),
            version=int(raw.get("version") or 1),
            steps=[PlanStep.from_dict(s) for s in steps_raw if isinstance(s, dict)],
            metadata=dict(raw.get("metadata") or {}),
        )

    def next_ready_step(self) -> Optional[PlanStep]:
        done = {
            step.id
            for step in self.steps
            if step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
        }
        for step in self.steps:
            if step.status not in {StepStatus.PENDING, StepStatus.READY}:
                continue
            if all(dep in done for dep in step.dependencies):
                return step
        return None


@dataclass
class Observation:
    source: str
    result: Any = None
    success: bool = True
    confidence: float = 1.0
    action_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _new_id("obs"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    execution_success: bool
    goal_success: bool
    needs_more_information: bool = False
    should_replan: bool = False
    confidence: float = 0.5
    reason: str = ""
    failure_class: FailureClass = FailureClass.NONE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["failure_class"] = self.failure_class.value
        return data


@dataclass
class CandidateAction:
    action: AgentActionKind
    rationale: str = ""
    expected_outcome: str = ""
    confidence: float = 0.5
    estimated_cost: float = 0.0
    risk: str = "low"
    required_permission: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    capability: Optional[str] = None
    step_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass
class RecoveryDecision:
    failure_class: FailureClass
    strategy: str
    should_retry: bool = False
    should_replan: bool = False
    should_switch_tool: bool = False
    should_ask_user: bool = False
    should_abort: bool = False
    alternate_tool: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["failure_class"] = self.failure_class.value
        return data


@dataclass
class DecisionTrace:
    goal_id: str
    decision: str
    reason: str
    tool: Optional[str] = None
    result_summary: str = ""
    next_action: str = ""
    evaluation: Optional[Dict[str, Any]] = None
    iteration: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _new_id("trace"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Budget:
    max_iterations: int = 6
    max_tool_calls: int = 8
    max_retries: int = 2
    max_replans: int = 2
    max_execution_time_s: float = 60.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeBudgetUsage:
    iterations: int = 0
    tool_calls: int = 0
    retries: int = 0
    replans: int = 0
    started_at: float = field(default_factory=time.time)

    def exceeded(self, budget: Budget) -> Optional[str]:
        if self.iterations >= budget.max_iterations:
            return "max_iterations"
        if self.tool_calls >= budget.max_tool_calls:
            return "max_tool_calls"
        if self.retries > budget.max_retries:
            return "max_retries"
        if self.replans > budget.max_replans:
            return "max_replans"
        elapsed = time.time() - self.started_at
        if elapsed >= budget.max_execution_time_s:
            return "max_execution_time"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "retries": self.retries,
            "replans": self.replans,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "RuntimeBudgetUsage":
        data = raw if isinstance(raw, dict) else {}
        usage = cls(
            iterations=int(data.get("iterations") or 0),
            tool_calls=int(data.get("tool_calls") or 0),
            retries=int(data.get("retries") or 0),
            replans=int(data.get("replans") or 0),
            started_at=float(data.get("started_at") or time.time()),
        )
        return usage


@dataclass
class PolicyConstraints:
    """Deterministic policy ceiling for candidate-plan approval."""

    owner_present: bool = False
    quiet_hours: bool = False
    dry_run: bool = False
    risk_ceiling: str = "medium"
    blocked_risks: List[str] = field(default_factory=lambda: ["critical"])
    allow_irreversible: bool = False
    max_steps: int = 4
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "PolicyConstraints":
        data = raw if isinstance(raw, dict) else {}
        return cls(
            owner_present=bool(data.get("owner_present", False)),
            quiet_hours=bool(data.get("quiet_hours", False)),
            dry_run=bool(data.get("dry_run", False)),
            risk_ceiling=str(data.get("risk_ceiling") or "medium"),
            blocked_risks=[str(r) for r in (data.get("blocked_risks") or ["critical"])],
            allow_irreversible=bool(data.get("allow_irreversible", False)),
            max_steps=int(data.get("max_steps") or 4),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ReplanContext:
    """Minimal structured context for observation-driven replanning."""

    original_goal: Goal
    current_plan: Plan
    failed_step: PlanStep
    observation: Observation
    evaluation: Evaluation
    recovery_history: List[Dict[str, Any]] = field(default_factory=list)
    available_capabilities: List[str] = field(default_factory=list)
    policy_constraints: PolicyConstraints = field(default_factory=PolicyConstraints)
    budget_remaining: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_goal": self.original_goal.to_dict(),
            "current_plan": self.current_plan.to_dict(),
            "failed_step": self.failed_step.to_dict(),
            "observation": self.observation.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "recovery_history": list(self.recovery_history),
            "available_capabilities": list(self.available_capabilities),
            "policy_constraints": self.policy_constraints.to_dict(),
            "budget_remaining": dict(self.budget_remaining),
            "metadata": dict(self.metadata),
        }


@dataclass
class CandidatePlan:
    """Planner output — never executed until PlanPolicyGate approves."""

    plan: Plan
    replan_reason: str = ""
    strategy_hint: str = ""
    source: str = "rules"  # rules | llm_assisted | fallback_observe_wait
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "replan_reason": self.replan_reason,
            "strategy_hint": self.strategy_hint,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass
class GoalSnapshot:
    """Durable companion intention across life-loop ticks (in-process)."""

    goal_id: str
    objective: str
    status: GoalStatus = GoalStatus.PENDING
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    current_plan: Optional[Dict[str, Any]] = None
    goal_plan: Optional[Dict[str, Any]] = None
    last_observation: Optional[Dict[str, Any]] = None
    last_evaluation: Optional[Dict[str, Any]] = None
    recovery_attempts: List[Dict[str, Any]] = field(default_factory=list)
    budget_usage: Dict[str, Any] = field(default_factory=dict)
    progress_signatures: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "objective": self.objective,
            "status": self.status.value,
            "params": dict(self.params),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "current_plan": self.current_plan,
            "goal_plan": self.goal_plan,
            "last_observation": self.last_observation,
            "last_evaluation": self.last_evaluation,
            "recovery_attempts": list(self.recovery_attempts),
            "budget_usage": dict(self.budget_usage),
            "progress_signatures": list(self.progress_signatures),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GoalSnapshot":
        status = raw.get("status", GoalStatus.PENDING)
        if isinstance(status, str):
            try:
                status = GoalStatus(status)
            except ValueError:
                status = GoalStatus.PENDING
        return cls(
            goal_id=str(raw.get("goal_id") or _new_id("goal")),
            objective=str(raw.get("objective") or ""),
            status=status,
            params=dict(raw.get("params") or {}),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            expires_at=raw.get("expires_at"),
            current_plan=raw.get("current_plan") if isinstance(raw.get("current_plan"), dict) else None,
            goal_plan=raw.get("goal_plan") if isinstance(raw.get("goal_plan"), dict) else None,
            last_observation=raw.get("last_observation") if isinstance(raw.get("last_observation"), dict) else None,
            last_evaluation=raw.get("last_evaluation") if isinstance(raw.get("last_evaluation"), dict) else None,
            recovery_attempts=list(raw.get("recovery_attempts") or []),
            budget_usage=dict(raw.get("budget_usage") or {}),
            progress_signatures=[str(s) for s in (raw.get("progress_signatures") or [])][-12:],
            metadata=dict(raw.get("metadata") or {}),
        )

    def has_executable_work(self) -> bool:
        plan = self.current_plan if isinstance(self.current_plan, dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("status") or "") in {StepStatus.READY.value, StepStatus.PENDING.value}:
                return True
        return False


class GoalCandidateSource(str, Enum):
    RULES = "rules"
    RESUME = "resume"
    RITUAL = "ritual"
    MODEL = "model"
    FALLBACK = "fallback"


class GoalFormationDisposition(str, Enum):
    SELECT = "select"
    DEFER = "defer"
    RESUME = "resume"
    SUPERSEDE = "supersede"


@dataclass
class NeedSignal:
    kind: str
    strength: float = 0.0
    id: str = field(default_factory=lambda: _new_id("need"))
    source: str = "needs_engine"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "strength": float(self.strength),
            "source": self.source,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "NeedSignal":
        return cls(
            id=str(raw.get("id") or _new_id("need")),
            kind=str(raw.get("kind") or "balance"),
            strength=float(raw.get("strength") or 0.0),
            source=str(raw.get("source") or "needs_engine"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class GoalCandidate:
    intent: str
    reason: str = ""
    description: str = ""
    candidate_id: str = field(default_factory=lambda: _new_id("cand"))
    source: GoalCandidateSource = GoalCandidateSource.RULES
    need_ids: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    expected_utility: float = 0.5
    urgency: float = 0.0
    confidence: float = 0.5
    novelty: float = 0.5
    estimated_cost: float = 0.3
    estimated_risk: float = 0.2
    deferable: bool = True
    continuity_of_goal_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "intent": self.intent,
            "description": self.description,
            "reason": self.reason,
            "source": self.source.value if isinstance(self.source, GoalCandidateSource) else str(self.source),
            "need_ids": list(self.need_ids),
            "required_capabilities": list(self.required_capabilities),
            "expected_utility": self.expected_utility,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "novelty": self.novelty,
            "estimated_cost": self.estimated_cost,
            "estimated_risk": self.estimated_risk,
            "deferable": self.deferable,
            "continuity_of_goal_id": self.continuity_of_goal_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GoalCandidate":
        source = raw.get("source", GoalCandidateSource.RULES)
        if isinstance(source, str):
            try:
                source = GoalCandidateSource(source)
            except ValueError:
                source = GoalCandidateSource.RULES
        return cls(
            candidate_id=str(raw.get("candidate_id") or _new_id("cand")),
            intent=str(raw.get("intent") or "calm_idle"),
            description=str(raw.get("description") or ""),
            reason=str(raw.get("reason") or ""),
            source=source,
            need_ids=list(raw.get("need_ids") or []),
            required_capabilities=list(raw.get("required_capabilities") or []),
            expected_utility=float(raw.get("expected_utility", 0.5)),
            urgency=float(raw.get("urgency", 0.0)),
            confidence=float(raw.get("confidence", 0.5)),
            novelty=float(raw.get("novelty", 0.5)),
            estimated_cost=float(raw.get("estimated_cost", 0.3)),
            estimated_risk=float(raw.get("estimated_risk", 0.2)),
            deferable=bool(raw.get("deferable", True)),
            continuity_of_goal_id=raw.get("continuity_of_goal_id"),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class GoalFormationContext:
    needs: List[NeedSignal] = field(default_factory=list)
    active_goal: Optional[GoalSnapshot] = None
    recent_goals: List[Dict[str, Any]] = field(default_factory=list)
    recent_outcome: Optional[Dict[str, Any]] = None
    available_capabilities: List[str] = field(default_factory=list)
    owner_present: bool = False
    quiet_hours: bool = False
    perception: Dict[str, Any] = field(default_factory=dict)
    mood: Dict[str, Any] = field(default_factory=dict)
    memory_hints: List[Dict[str, Any]] = field(default_factory=list)
    policy_constraints: PolicyConstraints = field(default_factory=PolicyConstraints)
    budget: Dict[str, Any] = field(default_factory=dict)
    dominant_need: str = "balance"
    recommended_goal: str = "calm_idle"
    scores: Dict[str, float] = field(default_factory=dict)
    trigger: str = "think_tick"
    previous_decision: Optional[Dict[str, Any]] = None
    context_fingerprint: str = ""
    now: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "needs": [n.to_dict() for n in self.needs],
            "active_goal": self.active_goal.to_dict() if self.active_goal else None,
            "recent_goals": list(self.recent_goals),
            "recent_outcome": self.recent_outcome,
            "available_capabilities": list(self.available_capabilities),
            "owner_present": self.owner_present,
            "quiet_hours": self.quiet_hours,
            "perception": dict(self.perception),
            "mood": dict(self.mood),
            "memory_hints": list(self.memory_hints),
            "policy_constraints": self.policy_constraints.to_dict(),
            "budget": dict(self.budget),
            "dominant_need": self.dominant_need,
            "recommended_goal": self.recommended_goal,
            "scores": dict(self.scores),
            "trigger": self.trigger,
            "previous_decision": self.previous_decision,
            "context_fingerprint": self.context_fingerprint,
            "now": self.now,
            "metadata": dict(self.metadata),
        }


@dataclass
class GoalFormationDecision:
    disposition: GoalFormationDisposition = GoalFormationDisposition.DEFER
    reason: str = ""
    selected_intent: Optional[str] = None
    selected_goal: Optional[Goal] = None
    selected_candidate: Optional[GoalCandidate] = None
    rejected: List[Dict[str, str]] = field(default_factory=list)
    candidates_considered: List[Dict[str, Any]] = field(default_factory=list)
    features: Dict[str, Any] = field(default_factory=dict)
    reused: bool = False
    superseded_goal_id: Optional[str] = None
    context_fingerprint: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "reason": self.reason,
            "selected_intent": self.selected_intent,
            "selected_goal": self.selected_goal.to_dict() if self.selected_goal else None,
            "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
            "rejected": list(self.rejected),
            "candidates_considered": list(self.candidates_considered),
            "features": dict(self.features),
            "reused": self.reused,
            "superseded_goal_id": self.superseded_goal_id,
            "context_fingerprint": self.context_fingerprint,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GoalFormationDecision":
        disposition = raw.get("disposition", GoalFormationDisposition.DEFER)
        if isinstance(disposition, str):
            try:
                disposition = GoalFormationDisposition(disposition)
            except ValueError:
                disposition = GoalFormationDisposition.DEFER
        goal_raw = raw.get("selected_goal")
        cand_raw = raw.get("selected_candidate")
        return cls(
            disposition=disposition,
            reason=str(raw.get("reason") or ""),
            selected_intent=raw.get("selected_intent"),
            selected_goal=Goal.from_dict(goal_raw) if isinstance(goal_raw, dict) else None,
            selected_candidate=GoalCandidate.from_dict(cand_raw) if isinstance(cand_raw, dict) else None,
            rejected=list(raw.get("rejected") or []),
            candidates_considered=list(raw.get("candidates_considered") or []),
            features=dict(raw.get("features") or {}),
            reused=bool(raw.get("reused", False)),
            superseded_goal_id=raw.get("superseded_goal_id"),
            context_fingerprint=str(raw.get("context_fingerprint") or ""),
            timestamp=float(raw.get("timestamp") or time.time()),
            metadata=dict(raw.get("metadata") or {}),
        )
