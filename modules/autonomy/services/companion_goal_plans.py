from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_companion_core import PetCompanionCore

logger = logging.getLogger("autonomy.companion_goal_plans")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalPlansMixin:
    """Planning, action trees, learning context, and pet companion core logic."""

    cfg: Dict[str, Any]
    enabled: bool
    behavior_planner: Any
    _last_event_ts: float
    _last_plan_key: str

    def _learning_context(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        policy = _as_dict(self.cfg.get("outcome_learning"))
        if not bool(policy.get("enabled", False)):
            return {}
        reflection = _as_dict(snapshot.get("reflection_policy") or snapshot.get("reflection"))
        outcome = _as_dict(
            snapshot.get("outcome_learning")
            or snapshot.get("companion_outcome")
            or snapshot.get("last_outcome")
        )
        raw_adjustments = _as_dict(reflection.get("candidate_weight_adjustments") or outcome.get("candidate_weight_adjustments"))
        limit = _as_float(policy.get("max_weight_adjustment"), 0.0)
        adjustments = {}
        for key, value in raw_adjustments.items():
            parsed = _as_float(value)
            if limit > 0.0:
                parsed = max(-limit, min(limit, parsed))
            adjustments[str(key)] = parsed
        return {
            "candidate_weight_adjustments": adjustments,
            "temporary_avoid_tags": [str(tag) for tag in (reflection.get("temporary_avoid_tags") or outcome.get("temporary_avoid_tags") or []) if str(tag)],
            "preferred_contexts": _as_dict(reflection.get("preferred_contexts") or outcome.get("preferred_contexts")),
        }

    def _pet_companion_decision(
        self,
        snap: Dict[str, Any],
        *,
        dominant: str,
        recommended: str,
        scores: Dict[str, Any],
        owner_present: bool,
    ) -> Dict[str, Any]:
        if not bool(self.cfg.get("pet_companion_enabled", True)):
            return {}
        score_map = _as_dict(scores)
        pet_needs = {
            "safety": _as_float(score_map.get("safety"), 0.0),
            "social": _as_float(score_map.get("social"), 0.0),
            "curiosity": _as_float(score_map.get("curiosity"), 0.0),
            "boredom": _as_float(score_map.get("boredom"), 0.0),
            "energy": _as_float(score_map.get("energy"), _as_float(snap.get("energy"), 0.7)),
            "dominant_need": dominant,
            "recommended_goal": recommended,
        }
        if dominant == "exploration":
            pet_needs["curiosity"] = max(pet_needs["curiosity"], 0.65)
        elif dominant == "rest":
            pet_needs["energy"] = min(pet_needs["energy"], 0.2)
        elif dominant == "social":
            pet_needs["social"] = max(pet_needs["social"], 0.65)
        elif dominant == "safety":
            pet_needs["safety"] = max(pet_needs["safety"], 0.75)
        elif dominant == "boredom":
            pet_needs["boredom"] = max(pet_needs["boredom"], 0.7)
        elif dominant == "curiosity":
            pet_needs["curiosity"] = max(pet_needs["curiosity"], 0.7)

        context = {
            "needs": pet_needs,
            "bond": _as_dict(snap.get("bond")),
            "routine": _as_dict(snap.get("routine")),
            "perception": {
                **_as_dict(snap.get("perception")),
                "owner_present": bool(owner_present),
            },
        }
        return PetCompanionCore().decide(context).as_dict()

    def _merge_pet_companion_plan(self, plan: Dict[str, Any], pet_companion: Dict[str, Any]) -> Dict[str, Any]:
        if not pet_companion:
            return plan
        out = dict(plan)
        actions = list(out.get("actions") or [])
        actions.append(
            {
                "type": "pet_intent",
                "name": str(pet_companion.get("intent") or ""),
                "expression_hint": str(pet_companion.get("expression_hint") or ""),
                "motion_hint": str(pet_companion.get("motion_hint") or ""),
                "speech_hint": str(pet_companion.get("speech_hint") or ""),
                "goal_hints": list(pet_companion.get("goal_hints") or []),
                "risk": "semantic",
            }
        )
        out["actions"] = actions
        out["pet_companion"] = pet_companion
        return out

    def _plan_for(self, dominant: str, recommended: str, *, scores: Dict[str, Any], owner_present: bool, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if recommended == "llm_behavior_planning" and self.behavior_planner:
            next_action = self.behavior_planner.get_next_action()
            if not next_action:
                recent_ref = snapshot.get("recent_reflections", []) if snapshot else []
                tool_schemas = snapshot.get("tool_schemas", []) if snapshot else []
                new_plan = self.behavior_planner.generate_plan(snapshot or {}, "Robot is currently idle.", recent_reflections=recent_ref, tool_schemas=tool_schemas)
                if new_plan:
                    next_action = self.behavior_planner.get_next_action()

            if next_action:
                return {
                    "behavior": "llm_generated_action",
                    "priority": "normal",
                    "expression_event": f"needs.{dominant}",
                    "safe_to_execute": True,
                    "actions": [next_action],
                }

        # Legacy path: need→template. Batch 5 preferred path is build_for_intent
        # after GoalFormationService approves an intent.
        try:
            from modules.agent_core.services.runtime import CompanionPlanAdapter

            adapter = getattr(self, "_companion_plan_adapter", None)
            if adapter is None:
                adapter = CompanionPlanAdapter()
                self._companion_plan_adapter = adapter
            return adapter.build(
                dominant,
                recommended,
                owner_present=owner_present,
                scores=scores,
            )
        except Exception as exc:
            logger.warning("CompanionPlanAdapter failed (%s); using calm_idle fallback", exc)
            return {
                "behavior": "calm_idle",
                "priority": "low",
                "expression_event": "needs.balance",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.balance"},
                    {"type": "wait", "label": "calm_idle", "risk": "none"},
                ],
            }

    def _event_for(self, plan_key: str, dominant: str, now_ts: float) -> str:
        if not self.enabled:
            return ""
        cooldown = max(1.0, _as_float(self.cfg.get("event_cooldown_s"), 12.0))
        if plan_key == self._last_plan_key and (now_ts - self._last_event_ts) < cooldown:
            return ""
        self._last_plan_key = plan_key
        self._last_event_ts = now_ts
        return f"goal.{dominant}"
