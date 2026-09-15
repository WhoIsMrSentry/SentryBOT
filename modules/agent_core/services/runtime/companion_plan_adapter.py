"""Companion need → typed Plan adapter using CapabilityIndex.

Converts domain need/behavior templates into schema-validated Plan/PlanStep
objects, resolves registry-backed capabilities, and emits legacy action dicts
compatible with CompanionGoalExecutor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .capability_index import CapabilityIndex
from .schemas import Goal, Plan, PlanStep, StepStatus


# Domain templates: need/behavior → capability steps.
# Selecting WHICH template is still a companion domain policy (needs model).
# Selecting WHETHER a step is available is capability-driven via CapabilityIndex.
_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "safety": {
        "behavior": "pause_and_observe",
        "priority": "critical",
        "expression_event": "needs.safety",
        "steps": [
            {
                "objective": "Express safety state",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.safety"},
            },
            {
                "objective": "Freeze motion",
                "capability": "motion.freeze",
                "action": {"type": "motion", "name": "freeze", "risk": "low"},
            },
            {
                "objective": "Cheap vision check",
                "capability": "vision.cheap",
                "action": {"type": "vision", "mode": "cheap", "reason": "safety"},
            },
        ],
    },
    "rest": {
        "behavior": "rest_in_safe_place",
        "priority": "low",
        "expression_event": "needs.rest",
        "steps": [
            {
                "objective": "Express rest state",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.rest"},
            },
            {
                "objective": "Move to rest corner",
                "capability": "navigation.rest_corner",
                "action": {
                    "type": "navigation",
                    "name": "rest_corner",
                    "policy": "rest_corner",
                    "risk": "low",
                },
            },
            {
                "objective": "Sleepy idle pose",
                "capability": "pose.sleepy_idle",
                "action": {"type": "pose", "name": "sleepy_idle", "risk": "low"},
            },
            {
                "objective": "Remain silent",
                "capability": "speech.silent",
                "action": {"type": "speech", "mode": "silent"},
            },
        ],
    },
    "social_absent": {
        "behavior": "seek_owner_or_invite_interaction",
        "priority": "normal",
        "expression_event": "needs.social",
        "steps": [
            {
                "objective": "Express social need",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.social"},
            },
            {
                "objective": "Scan for owner",
                "capability": "perception.owner_scan",
                "action": {"type": "perception", "name": "owner_scan", "risk": "low"},
            },
            {
                "objective": "Invite interaction",
                "capability": "speech.short_prompt",
                "action": {"type": "speech", "mode": "short_prompt", "template": "social_invite"},
            },
        ],
    },
    "social_present": {
        "behavior": "engage_owner",
        "priority": "normal",
        "expression_event": "needs.social",
        "steps": [
            {
                "objective": "Express social need",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.social"},
            },
            {
                "objective": "Scan for owner",
                "capability": "perception.owner_scan",
                "action": {"type": "perception", "name": "owner_scan", "risk": "low"},
            },
            {
                "objective": "Invite interaction",
                "capability": "speech.short_prompt",
                "action": {"type": "speech", "mode": "short_prompt", "template": "social_invite"},
            },
        ],
    },
    "exploration": {
        "behavior": "look_around_and_learn",
        "priority": "normal",
        "expression_event": "needs.exploration",
        "steps": [
            {
                "objective": "Express exploration",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.exploration"},
            },
            {
                "objective": "Cheap vision sample",
                "capability": "vision.cheap",
                "action": {"type": "vision", "mode": "cheap", "reason": "exploration"},
            },
            {
                "objective": "Look around",
                "capability": "motion.look_around",
                "action": {"type": "motion", "name": "look_around", "risk": "low"},
            },
        ],
    },
    "boredom": {
        "behavior": "scan_for_company_then_rest",
        "priority": "normal",
        "expression_event": "needs.boredom",
        "steps": [
            {
                "objective": "Express boredom",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.boredom"},
            },
            {
                "objective": "Stretch or scan",
                "capability": "motion.stretch_or_scan",
                "action": {"type": "motion", "name": "stretch_or_scan", "risk": "low"},
            },
            {
                "objective": "Cheap vision sample",
                "capability": "vision.cheap",
                "action": {"type": "vision", "mode": "cheap", "reason": "boredom"},
            },
            {
                "objective": "Track person",
                "capability": "perception.track_object",
                "action": {
                    "type": "perception",
                    "name": "track_person",
                    "label": "person",
                    "strategy": "center",
                    "risk": "low",
                },
            },
            {
                "objective": "Remember observation",
                "capability": "memory.observe",
                "action": {
                    "type": "memory",
                    "name": "observe",
                    "kind": "episode",
                    "summary": "Robot was bored and scanned for company.",
                    "risk": "none",
                },
            },
        ],
    },
    "sound": {
        "behavior": "inspect_sound_source",
        "priority": "high",
        "expression_event": "needs.sound_attention",
        "steps": [
            {
                "objective": "Express sound attention",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.sound_attention"},
            },
            {
                "objective": "Attend to source",
                "capability": "motion.attend",
                "action": {"type": "motion", "name": "attend", "risk": "low"},
            },
            {
                "objective": "Track person",
                "capability": "perception.track_object",
                "action": {
                    "type": "perception",
                    "name": "track_person",
                    "label": "person",
                    "strategy": "center",
                    "risk": "low",
                },
            },
            {
                "objective": "Cheap vision sample",
                "capability": "vision.cheap",
                "action": {"type": "vision", "mode": "cheap", "reason": "sound_interrupt"},
            },
        ],
    },
    "curiosity": {
        "behavior": "inspect_environment_and_learn",
        "priority": "normal",
        "expression_event": "needs.curiosity",
        "steps": [
            {
                "objective": "Express curiosity",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.curiosity"},
            },
            {
                "objective": "Cheap vision sample",
                "capability": "vision.cheap",
                "action": {"type": "vision", "mode": "cheap", "reason": "curiosity"},
            },
            {
                "objective": "Semantic vision refresh",
                "capability": "vision.semantic",
                "action": {"type": "vision", "mode": "semantic", "reason": "curiosity_unknown"},
            },
            {
                "objective": "Attend",
                "capability": "motion.attend",
                "action": {"type": "motion", "name": "attend", "risk": "low"},
            },
        ],
    },
    "balance": {
        "behavior": "calm_idle",
        "priority": "low",
        "expression_event": "needs.balance",
        "steps": [
            {
                "objective": "Express balance",
                "capability": "expression.event",
                "action": {"type": "expression", "event": "needs.balance"},
            },
            {
                "objective": "Wait calmly",
                "capability": "scheduler.wait",
                "action": {"type": "wait", "label": "calm_idle", "risk": "none"},
            },
        ],
    },
}


# Approved formation intents → existing planning templates (HOW compatibility only).
INTENT_TO_TEMPLATE: Dict[str, str] = {
    "pause_and_observe": "safety",
    "settle_or_rest": "rest",
    "rest_in_safe_place": "rest",
    "social_check_in": "social_present",
    "engage_owner": "social_present",
    "seek_owner_or_invite": "social_absent",
    "look_around_and_learn": "exploration",
    "inspect_environment": "curiosity",
    "inspect_environment_and_learn": "curiosity",
    "inspect_sound_source": "sound",
    "scan_for_company_then_rest": "boredom",
    "calm_idle": "balance",
}


def select_template_key(
    dominant: str,
    recommended: str,
    *,
    owner_present: bool,
) -> str:
    """Legacy need→template mapping (compat). Prefer build_for_intent for Batch 5+."""
    dom = str(dominant or "").strip().lower()
    rec = str(recommended or "").strip().lower()
    if dom == "safety":
        return "safety"
    if rec == "rest_in_safe_place" or dom == "rest":
        return "rest"
    if dom == "social":
        return "social_present" if owner_present else "social_absent"
    if dom == "exploration":
        return "exploration"
    if rec == "look_for_company_or_rest" or dom == "boredom":
        return "boredom"
    if rec == "inspect_sound_source":
        return "sound"
    if dom == "curiosity":
        return "curiosity"
    return "balance"


class CompanionPlanAdapter:
    """Build typed Plans from companion templates + CapabilityIndex.

    Batch 5 path: build_for_intent(approved intent) — HOW only.
    Legacy path: build(dominant, recommended) — retained for compatibility.
    """

    def __init__(self, capability_index: Optional[CapabilityIndex] = None) -> None:
        self.capabilities = capability_index or CapabilityIndex.from_robot_registry()

    def build_for_intent(
        self,
        intent: str,
        *,
        goal: Optional[Goal] = None,
        context: Optional[Dict[str, Any]] = None,
        scores: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Plan for an already-approved formation intent (does not select intention)."""
        ctx = context if isinstance(context, dict) else {}
        key = INTENT_TO_TEMPLATE.get(str(intent or "").strip().lower(), "balance")
        # Owner-sensitive social intents already resolved upstream; keep template key stable.
        if intent == "social_check_in":
            key = "social_present"
        elif intent == "seek_owner_or_invite":
            key = "social_absent"
        return self._build_from_template(
            key,
            goal=goal,
            intent=str(intent),
            scores=scores,
            owner_present=bool(ctx.get("owner_present", False)),
            dominant_need=str(ctx.get("dominant_need") or ""),
            recommended_goal=str(ctx.get("recommended_goal") or intent),
        )

    def build(
        self,
        dominant: str,
        recommended: str,
        *,
        owner_present: bool = False,
        scores: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = select_template_key(dominant, recommended, owner_present=owner_present)
        goal = Goal(
            id=goal_id or f"companion_{key}",
            objective=f"Satisfy companion need '{dominant}' via template '{key}'",
            priority=_priority_score(str((_TEMPLATES.get(key) or {}).get("priority") or "low")),
            metadata={
                "dominant_need": dominant,
                "recommended_goal": recommended,
                "template": key,
                "scores": dict(scores or {}),
                "owner_present": bool(owner_present),
                "legacy_build": True,
            },
        )
        return self._build_from_template(
            key,
            goal=goal,
            intent=str(recommended or dominant or key),
            scores=scores,
            owner_present=owner_present,
            dominant_need=dominant,
            recommended_goal=recommended,
        )

    def _build_from_template(
        self,
        key: str,
        *,
        goal: Optional[Goal],
        intent: str,
        scores: Optional[Dict[str, Any]],
        owner_present: bool,
        dominant_need: str,
        recommended_goal: str,
    ) -> Dict[str, Any]:
        template = dict(_TEMPLATES.get(key) or _TEMPLATES["balance"])
        if goal is None:
            goal = Goal(
                id=f"companion_{key}",
                objective=str(template.get("behavior") or intent),
                priority=_priority_score(str(template.get("priority") or "low")),
                metadata={},
            )
        goal.metadata = {
            **dict(goal.metadata or {}),
            "intent": intent,
            "dominant_need": dominant_need,
            "recommended_goal": recommended_goal,
            "template": key,
            "scores": dict(scores or {}),
            "owner_present": bool(owner_present),
        }

        plan_steps: List[PlanStep] = []
        actions: List[Dict[str, Any]] = []
        gaps: List[Dict[str, str]] = []
        prev_id: Optional[str] = None

        for raw in list(template.get("steps") or []):
            if not isinstance(raw, dict):
                continue
            capability = str(raw.get("capability") or "").strip()
            action = dict(raw.get("action") or {})
            if capability:
                action.setdefault("capability", capability)
            enabled = self.capabilities.is_capability_enabled(capability) if capability else True
            if capability and not enabled:
                gaps.append(
                    {
                        "missing_capability": capability,
                        "reason": "capability_disabled_in_registry",
                        "suggested_integration": "",
                    }
                )
                step = PlanStep(
                    objective=str(raw.get("objective") or capability),
                    required_capabilities=[capability] if capability else [],
                    dependencies=[prev_id] if prev_id else [],
                    status=StepStatus.SKIPPED,
                    metadata={"action": action, "skipped": True, "reason": "disabled"},
                )
                plan_steps.append(step)
                prev_id = step.id
                continue

            if capability and not self.capabilities.has_registry_capability(capability):
                gaps.append(
                    {
                        "missing_capability": capability,
                        "reason": "not_in_registry",
                        "suggested_integration": "",
                    }
                )

            tools = self.capabilities.tools_for_capability(capability) if capability else []
            step = PlanStep(
                objective=str(raw.get("objective") or capability or "step"),
                required_capabilities=[capability] if capability else [],
                preferred_tools=list(tools[:2]),
                dependencies=[prev_id] if prev_id else [],
                status=StepStatus.READY,
                success_criteria=[],
                metadata={"action": action, "risk": str(action.get("risk") or "low")},
            )
            plan_steps.append(step)
            actions.append(action)
            prev_id = step.id

        plan = Plan(goal_id=goal.id, steps=plan_steps, metadata={"template": key, "intent": intent})
        return {
            "behavior": str(template.get("behavior") or intent or "calm_idle"),
            "priority": str(template.get("priority") or "low"),
            "expression_event": str(template.get("expression_event") or f"needs.{dominant_need or 'balance'}"),
            "safe_to_execute": True,
            "actions": actions,
            "typed_goal": goal.to_dict(),
            "typed_plan": plan.to_dict(),
            "capability_gaps": gaps,
            "template_key": key,
            "intent": intent,
        }


def _priority_score(priority: str) -> float:
    return {"critical": 1.0, "high": 0.85, "normal": 0.55, "low": 0.25}.get(str(priority).lower(), 0.5)
