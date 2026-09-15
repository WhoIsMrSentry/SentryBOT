"""Policy boundary for candidate plans — approves or rejects, never plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .capability_index import CapabilityIndex
from .schemas import CandidatePlan, Plan, PolicyConstraints, ReplanContext, StepStatus

_RISK_RANK = {"none": 0, "low": 1, "semantic": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class ApprovedPlan:
    plan: Plan
    candidate: CandidatePlan
    reason: str = "approved"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "approved": True,
            "reason": self.reason,
            "plan": self.plan.to_dict(),
            "candidate": self.candidate.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass
class Reject:
    reason: str
    candidate: Optional[CandidatePlan] = None
    violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "approved": False,
            "reason": self.reason,
            "violations": list(self.violations),
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "metadata": dict(self.metadata),
        }


class PlanPolicyGate:
    """Deterministic safety/capability filter for CandidatePlan objects."""

    def __init__(
        self,
        *,
        capabilities: Optional[CapabilityIndex] = None,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.capabilities = capabilities if capabilities is not None else CapabilityIndex.from_robot_registry()
        self.default_max_steps = max(1, int(raw.get("max_candidate_steps", 4)))
        self.default_risk_ceiling = str(raw.get("risk_ceiling") or "medium")
        blocked = raw.get("blocked_risks")
        self.default_blocked = [str(r) for r in blocked] if isinstance(blocked, list) else ["critical"]

    def approve(
        self,
        candidate: CandidatePlan,
        context: Optional[ReplanContext] = None,
    ) -> Union[ApprovedPlan, Reject]:
        if candidate is None or not isinstance(candidate.plan, Plan):
            return Reject(reason="invalid_candidate", violations=["missing_plan"])

        constraints = context.policy_constraints if context is not None else PolicyConstraints()
        plan = candidate.plan
        violations: List[str] = []
        available = set(context.available_capabilities) if context is not None else set()
        registry_loaded = bool(self.capabilities.describe().get("registry_capability_count"))

        max_steps = int(constraints.max_steps or self.default_max_steps)
        if len(plan.steps) == 0:
            violations.append("empty_plan")
        if len(plan.steps) > max_steps:
            violations.append("max_steps_exceeded")

        if constraints.quiet_hours:
            for step in plan.steps:
                cap = self._cap(step)
                if cap.startswith(("speech.", "motion.", "navigation.", "expression.")):
                    violations.append(f"quiet_hours_blocks:{cap}")

        risk_ceiling = str(constraints.risk_ceiling or self.default_risk_ceiling)
        blocked = set(constraints.blocked_risks or self.default_blocked)
        budget = context.budget_remaining if context is not None else {}
        if budget.get("replans_remaining") is not None and int(budget.get("replans_remaining") or 0) < 0:
            violations.append("budget_replans_exhausted")

        for step in plan.steps:
            cap = self._cap(step)
            if not cap:
                violations.append(f"missing_capability:{step.id}")
                continue
            if not self.capabilities.is_capability_enabled(cap):
                violations.append(f"capability_disabled:{cap}")
                continue
            if registry_loaded and not self.capabilities.has_registry_capability(cap):
                violations.append(f"capability_unavailable:{cap}")
            elif available and cap not in available:
                violations.append(f"capability_unavailable:{cap}")

            meta = self.capabilities.registry_meta(cap)
            action = (step.metadata or {}).get("action") if isinstance((step.metadata or {}).get("action"), dict) else {}
            meta_risk = str(meta.get("risk") or "low").lower()
            step_risk = str((step.metadata or {}).get("risk") or action.get("risk") or meta_risk).lower()
            # Prefer the higher declared risk (step metadata can tighten, never loosen below registry).
            risk = (
                step_risk
                if _RISK_RANK.get(step_risk, -1) >= _RISK_RANK.get(meta_risk, -1)
                else meta_risk
            )
            if risk in blocked:
                violations.append(f"blocked_risk:{cap}:{risk}")
            if _RISK_RANK.get(risk, 9) > _RISK_RANK.get(risk_ceiling, 2):
                violations.append(f"risk_ceiling:{cap}:{risk}>{risk_ceiling}")
            if risk in {"high", "critical"} and not constraints.allow_irreversible:
                violations.append(f"irreversible_without_permission:{cap}")

            if step.status not in {StepStatus.PENDING, StepStatus.READY, StepStatus.RUNNING}:
                violations.append(f"invalid_step_status:{step.id}:{step.status}")

        unique: List[str] = []
        seen = set()
        for item in violations:
            if item not in seen:
                seen.add(item)
                unique.append(item)

        if unique:
            return Reject(reason="policy_rejected", candidate=candidate, violations=unique)

        return ApprovedPlan(plan=plan, candidate=candidate, reason="approved")

    @staticmethod
    def _cap(step) -> str:
        if step.required_capabilities:
            return str(step.required_capabilities[0])
        action = step.metadata.get("action") if isinstance(step.metadata.get("action"), dict) else {}
        return str(action.get("capability") or "")


__all__ = ["PlanPolicyGate", "ApprovedPlan", "Reject"]
