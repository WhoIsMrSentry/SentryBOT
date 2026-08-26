from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_companion_core import PetCompanionCore
from .companion_goal_policies import CompanionGoalPoliciesMixin, _as_float, _as_dict
from .companion_goal_plans import CompanionGoalPlansMixin

PET_COMPANION_GOAL_SELECTOR_INTEGRATION_CONTRACT = True
PET_COMPANION_GOAL_SELECTOR_INTEGRATION_ROLE = "pet_core_side_channel_for_goal_selector"


class CompanionGoalSelector(CompanionGoalPoliciesMixin, CompanionGoalPlansMixin):
    """Turn companion needs into a semantic goal plan.

    This class does not drive hardware. It produces a safe, inspectable plan
    that can later be executed by capability/safety layers. This keeps the
    companion behavior semantic: needs -> goal -> expression/capability plan.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "event_cooldown_s": 12.0,
        "auto_execute": True,
        "pet_companion_enabled": True,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self.enabled = bool(self.cfg.get("enabled", True))
        self._last_event_ts: float = 0.0
        self._last_plan_key: str = ""
        environment_policy = _as_dict(self.cfg.get("environment_policy"))
        try:
            seed = int(environment_policy.get("seed", 0))
        except (TypeError, ValueError):
            seed = 0
        self._rng = random.Random(seed)
        
        try:
            from modules.autonomy.services.behavior_planner import BehaviorPlanner
            self.behavior_planner = BehaviorPlanner(self.cfg)
        except ImportError:
            self.behavior_planner = None

    def select(
        self,
        needs_snapshot: Optional[Dict[str, Any]],
        *,
        owner_present: bool = False,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        snap = _as_dict(needs_snapshot)
        dominant = str(snap.get("dominant_need") or "balance").strip().lower()
        recommended = str(snap.get("recommended_goal") or "calm_idle").strip().lower()
        confidence = max(0.0, min(1.0, _as_float(snap.get("confidence"), 0.55)))
        scores = dict(_as_dict(snap.get("scores")))
        learning = self._learning_context(snap)
        for need, adjustment in learning.get("candidate_weight_adjustments", {}).items():
            if need in scores:
                scores[need] = max(0.0, _as_float(scores.get(need)) + _as_float(adjustment))

        plan = self._plan_for(dominant, recommended, scores=scores, owner_present=owner_present, snapshot=snap)
        pet_companion = self._pet_companion_decision(
            snap,
            dominant=dominant,
            recommended=recommended,
            scores=scores,
            owner_present=owner_present,
        )
        plan = self._merge_pet_companion_plan(plan, pet_companion)
        plan_key = f"{dominant}:{recommended}:{plan.get('behavior')}"
        event = self._event_for(plan_key, dominant, ts)

        auto_execute = bool(self.cfg.get("auto_execute", True))

        out: Dict[str, Any] = {
            "ok": True,
            "available": bool(self.enabled),
            "timestamp": ts,
            "plan_id": plan_key,
            "dominant_need": dominant,
            "recommended_goal": recommended,
            "behavior": plan.get("behavior", "calm_idle"),
            "pet_companion": pet_companion,
            "pet_intent": str(pet_companion.get("intent") or ""),
            "pet_expression_hint": str(pet_companion.get("expression_hint") or ""),
            "pet_motion_hint": str(pet_companion.get("motion_hint") or ""),
            "pet_speech_hint": str(pet_companion.get("speech_hint") or ""),
            "pet_goal_hints": list(pet_companion.get("goal_hints") or []),
            "pet_needs_bias": dict(pet_companion.get("needs_bias") or {}),
            "pet_memory_tags": list(pet_companion.get("memory_tags") or []),
            "priority": plan.get("priority", "low"),
            "confidence": round(confidence, 2),
            "reason": f"needs.{dominant}",
            "event": event,
            "expression_event": plan.get("expression_event", f"needs.{dominant}"),
            "expression_data": {
                "recommended_goal": recommended,
                "confidence": round(confidence, 2),
                "dominant_need": dominant,
            },
            "actions": plan.get("actions", []),
            "safe_to_execute": bool(plan.get("safe_to_execute", True)),
            "auto_execute": auto_execute,
            "owner_present": bool(owner_present),
            "scores": {k: round(_as_float(v), 1) for k, v in scores.items()},
        }
        out = self._apply_environment_policy(out, snapshot=snap, owner_present=owner_present, timestamp=ts)
        out = self._apply_uncertainty_policy(out, snapshot=snap)
        out = self._apply_personalization_policy(out, snapshot=snap)
        out = self._apply_privacy_policy(out, snapshot=snap)
        out = self._apply_capability_health_policy(out, snapshot=snap)
        out = self._apply_outcome_learning_policy(out, snapshot=snap)
        out = self._apply_social_policy(out, snapshot=snap, owner_present=owner_present)
        out["config_source"] = {
            "root": "companion_goals",
            "policies": {
                "uncertainty": "companion_goals.autonomy_policy.uncertainty",
                "personalization": "companion_goals.autonomy_policy.personalization",
                "privacy": "companion_goals.autonomy_policy.privacy",
                "explanation": "companion_goals.autonomy_policy.explanation",
                "capability_health": "companion_goals.autonomy_policy.health",
                "environment": "companion_goals.environment_policy",
                "outcome_learning": "outcome_learning",
                "social": "social_policy",
                "pet_companion": "companion_goals.pet_companion_enabled",
            },
        }
        return self._apply_explanation_policy(out)
