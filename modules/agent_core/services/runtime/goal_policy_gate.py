"""Intention-level policy gate — distinct from PlanPolicyGate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .capability_index import CapabilityIndex
from .goal_candidate_generator import ALLOWED_INTENTS
from .schemas import GoalCandidate, GoalFormationContext

SIDE_EFFECT_INTENTS = frozenset(
    {
        "social_check_in",
        "seek_owner_or_invite",
        "settle_or_rest",
        "look_around_and_learn",
        "inspect_sound_source",
        "scan_for_company_then_rest",
    }
)


@dataclass
class GoalApproval:
    candidate: GoalCandidate
    reason: str = "approved"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalReject:
    candidate: GoalCandidate
    reason: str
    violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GoalPolicyGate:
    """Reject inappropriate intentions before planning."""

    def __init__(
        self,
        *,
        capabilities: Optional[CapabilityIndex] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.capabilities = capabilities if capabilities is not None else CapabilityIndex.from_robot_registry()
        self.risk_ceiling = str(raw.get("risk_ceiling") or "medium")
        self.blocked_intents = {str(x) for x in (raw.get("blocked_intents") or [])}

    def approve(
        self,
        candidate: GoalCandidate,
        context: GoalFormationContext,
    ) -> Union[GoalApproval, GoalReject]:
        violations: List[str] = []
        intent = str(candidate.intent or "")
        if intent not in ALLOWED_INTENTS:
            violations.append(f"unknown_intent:{intent}")
        if intent in self.blocked_intents:
            violations.append(f"blocked_intent:{intent}")

        if context.quiet_hours and intent in SIDE_EFFECT_INTENTS:
            violations.append("quiet_hours_blocks_intent")

        prefs = {}
        if isinstance(context.metadata.get("preferences"), dict):
            prefs = context.metadata.get("preferences") or {}
        if bool(prefs.get("quiet_mode")) and intent in {"social_check_in", "seek_owner_or_invite"}:
            violations.append("quiet_mode_blocks_social")
        if bool(prefs.get("no_follow")) and intent in {"seek_owner_or_invite"}:
            violations.append("no_follow_preference")

        available = set(context.available_capabilities or [])
        required = list(candidate.required_capabilities or [])
        if intent == "resume_existing_goal":
            required = []
        for cap in required:
            if not self.capabilities.is_capability_enabled(cap):
                violations.append(f"capability_disabled:{cap}")
            elif available and cap not in available and self.capabilities.has_registry_capability(cap) is False:
                violations.append(f"capability_unavailable:{cap}")
            elif available and self.capabilities.describe().get("registry_capability_count"):
                if not self.capabilities.has_registry_capability(cap) and cap not in available:
                    violations.append(f"capability_unavailable:{cap}")
            elif self.capabilities.describe().get("registry_capability_count"):
                if not self.capabilities.has_registry_capability(cap):
                    # Soft: registry loaded but capability missing
                    if cap not in available:
                        violations.append(f"capability_unavailable:{cap}")

        if float(candidate.estimated_risk) > 0.8 and not context.policy_constraints.allow_irreversible:
            violations.append("risk_too_high")

        # Budget pressure: expensive intents when iterations nearly exhausted
        budget = context.budget or {}
        if budget.get("low_budget") and float(candidate.estimated_cost) >= 0.4 and candidate.deferable:
            violations.append("budget_pressure")

        unique = []
        seen = set()
        for item in violations:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        if unique:
            return GoalReject(candidate=candidate, reason="goal_policy_rejected", violations=unique)
        return GoalApproval(candidate=candidate, reason="approved")


__all__ = ["GoalPolicyGate", "GoalApproval", "GoalReject"]
