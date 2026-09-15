"""Agent cognitive runtime package — schemas, recovery, capabilities, traces."""

from __future__ import annotations

from .capability_index import CapabilityIndex, DEFAULT_TOOL_CAPABILITIES
from .companion_execution_loop import CompanionExecutionLoop, observation_replan
from .companion_plan_adapter import INTENT_TO_TEMPLATE, CompanionPlanAdapter, select_template_key
from .contextual_replanner import ContextualReplanner
from .decision_trace import DecisionTraceStore, to_public_trace
from .goal_candidate_generator import ALLOWED_INTENTS, GoalCandidateGenerator
from .goal_evaluator import GoalEvaluator
from .goal_formation import GoalFormationService, needs_from_snapshot
from .goal_policy_gate import GoalApproval, GoalPolicyGate, GoalReject
from .goal_store import GoalStore
from .native_tool_recovery import NativeToolRecovery, READ_ONLY_TOOLS
from .plan_policy_gate import ApprovedPlan, PlanPolicyGate, Reject
from .progress_tracker import ProgressTracker
from .recovery import FailureClassifier, RecoveryManager
from .runtime import AgentRuntime
from .schemas import (
    AgentActionKind,
    Budget,
    CandidateAction,
    CandidatePlan,
    DecisionTrace,
    Evaluation,
    FailureClass,
    Goal,
    GoalCandidate,
    GoalCandidateSource,
    GoalFormationContext,
    GoalFormationDecision,
    GoalFormationDisposition,
    GoalSnapshot,
    GoalStatus,
    NeedSignal,
    Observation,
    Plan,
    PlanStep,
    PolicyConstraints,
    RecoveryDecision,
    ReplanContext,
    RuntimeState,
    StepStatus,
)

__all__ = [
    "ALLOWED_INTENTS",
    "AgentActionKind",
    "AgentRuntime",
    "ApprovedPlan",
    "Budget",
    "CandidateAction",
    "CandidatePlan",
    "CapabilityIndex",
    "CompanionExecutionLoop",
    "CompanionPlanAdapter",
    "ContextualReplanner",
    "DEFAULT_TOOL_CAPABILITIES",
    "DecisionTrace",
    "DecisionTraceStore",
    "Evaluation",
    "FailureClass",
    "FailureClassifier",
    "Goal",
    "GoalApproval",
    "GoalCandidate",
    "GoalCandidateGenerator",
    "GoalCandidateSource",
    "GoalEvaluator",
    "GoalFormationContext",
    "GoalFormationDecision",
    "GoalFormationDisposition",
    "GoalFormationService",
    "GoalPolicyGate",
    "GoalReject",
    "GoalSnapshot",
    "GoalStatus",
    "GoalStore",
    "INTENT_TO_TEMPLATE",
    "NativeToolRecovery",
    "NeedSignal",
    "Observation",
    "Plan",
    "PlanPolicyGate",
    "PlanStep",
    "PolicyConstraints",
    "ProgressTracker",
    "READ_ONLY_TOOLS",
    "RecoveryDecision",
    "RecoveryManager",
    "Reject",
    "ReplanContext",
    "RuntimeState",
    "StepStatus",
    "needs_from_snapshot",
    "observation_replan",
    "select_template_key",
    "to_public_trace",
]
