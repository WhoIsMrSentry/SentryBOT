from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_companion_core import PetCompanionCore
from .companion_goal_policies import CompanionGoalPoliciesMixin, _as_float, _as_dict
from .companion_goal_plans import CompanionGoalPlansMixin

import logging

logger = logging.getLogger("autonomy.companion_goal_selector")

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
        self._last_companion_plan: Dict[str, Any] = {}
        self.goal_formation = None
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

        formation_cfg = _as_dict(self.cfg.get("goal_formation"))
        if formation_cfg.get("enabled", True):
            try:
                from modules.agent_core.services.runtime.goal_formation import GoalFormationService

                self.goal_formation = GoalFormationService(cfg=formation_cfg)
            except Exception:
                self.goal_formation = None

    def set_goal_formation(self, service: Any) -> None:
        self.goal_formation = service

    def select(
        self,
        needs_snapshot: Optional[Dict[str, Any]],
        *,
        owner_present: bool = False,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        snap = _as_dict(needs_snapshot)
        # Inject recent outcome for formation repetition / learning signals
        if "companion_outcome" not in snap and "last_outcome" not in snap:
            outcome = _as_dict(self.cfg.get("_runtime_companion_outcome"))
            if outcome:
                snap["companion_outcome"] = outcome

        dominant = str(snap.get("dominant_need") or "balance").strip().lower()
        recommended = str(snap.get("recommended_goal") or "calm_idle").strip().lower()
        confidence = max(0.0, min(1.0, _as_float(snap.get("confidence"), 0.55)))
        scores = dict(_as_dict(snap.get("scores")))
        learning = self._learning_context(snap)
        for key, adjustment in learning.get("candidate_weight_adjustments", {}).items():
            key_s = str(key)
            if key_s in scores:
                scores[key_s] = max(0.0, _as_float(scores.get(key_s)) + _as_float(adjustment))
            # Intent-keyed adjustments boost/penalize related need proxies lightly.
            elif key_s in {"inspect_environment", "look_around_and_learn", "inspect_sound_source"}:
                scores["curiosity"] = max(0.0, _as_float(scores.get("curiosity")) + _as_float(adjustment))
            elif key_s in {"social_check_in", "seek_owner_or_invite"}:
                scores["social"] = max(0.0, _as_float(scores.get("social")) + _as_float(adjustment))
            elif key_s in {"settle_or_rest"}:
                scores["rest"] = max(0.0, _as_float(scores.get("rest")) + _as_float(adjustment))
            elif key_s == "pause_and_observe":
                scores["safety"] = max(0.0, _as_float(scores.get("safety")) + _as_float(adjustment))
        snap["scores"] = scores

        formation_decision = None
        if self.goal_formation is not None and bool(_as_dict(self.cfg.get("goal_formation")).get("enabled", True)):
            formation_decision = self.goal_formation.form(
                snap,
                owner_present=owner_present,
                now=ts,
                previous_plan=self._last_companion_plan or None,
            )
            plan = self._plan_from_formation(
                formation_decision,
                dominant=dominant,
                recommended=recommended,
                scores=scores,
                owner_present=owner_present,
                snapshot=snap,
            )
        else:
            plan = self._plan_for(dominant, recommended, scores=scores, owner_present=owner_present, snapshot=snap)

        pet_companion = self._pet_companion_decision(
            snap,
            dominant=dominant,
            recommended=recommended,
            scores=scores,
            owner_present=owner_present,
        )
        if not bool(plan.get("deferred")):
            plan = self._merge_pet_companion_plan(plan, pet_companion)

        intent = str(plan.get("intent") or recommended)
        plan_key = f"{dominant}:{intent}:{plan.get('behavior')}"
        event = self._event_for(plan_key, dominant, ts)

        auto_execute = bool(self.cfg.get("auto_execute", True))
        if bool(plan.get("deferred")):
            auto_execute = False

        out: Dict[str, Any] = {
            "ok": True,
            "available": bool(self.enabled),
            "timestamp": ts,
            "plan_id": plan_key,
            "dominant_need": dominant,
            "recommended_goal": recommended,
            "intent": intent,
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
            "reason": str(plan.get("reason") or f"needs.{dominant}"),
            "event": event if not plan.get("deferred") else "",
            "expression_event": plan.get("expression_event", f"needs.{dominant}"),
            "expression_data": {
                "recommended_goal": recommended,
                "confidence": round(confidence, 2),
                "dominant_need": dominant,
                "intent": intent,
            },
            "actions": list(plan.get("actions") or []),
            "safe_to_execute": bool(plan.get("safe_to_execute", True)) and not bool(plan.get("deferred")),
            "auto_execute": auto_execute,
            "owner_present": bool(owner_present),
            "scores": {k: round(_as_float(v), 1) for k, v in scores.items()},
            "typed_goal": plan.get("typed_goal"),
            "typed_plan": plan.get("typed_plan"),
            "capability_gaps": list(plan.get("capability_gaps") or []),
            "template_key": plan.get("template_key"),
            "deferred": bool(plan.get("deferred")),
            "goal_formation": formation_decision.to_dict() if formation_decision is not None else None,
            "formation_disposition": (
                formation_decision.disposition.value if formation_decision is not None else "legacy"
            ),
        }
        if not out["deferred"]:
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
                "goal_formation": "companion_goals.goal_formation",
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
        out = self._apply_explanation_policy(out)
        self._last_companion_plan = dict(out)
        return out

    def _plan_from_formation(
        self,
        decision: Any,
        *,
        dominant: str,
        recommended: str,
        scores: Dict[str, Any],
        owner_present: bool,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        from modules.agent_core.services.runtime.schemas import GoalFormationDisposition

        if decision is None or decision.disposition == GoalFormationDisposition.DEFER:
            return {
                "behavior": "deferred",
                "priority": "low",
                "expression_event": "",
                "safe_to_execute": False,
                "actions": [],
                "deferred": True,
                "reason": getattr(decision, "reason", "deferred"),
                "intent": None,
            }

        if decision.disposition == GoalFormationDisposition.RESUME:
            goal_plan = dict((decision.metadata or {}).get("goal_plan") or {})
            if goal_plan:
                goal_plan = dict(goal_plan)
                goal_plan["deferred"] = False
                goal_plan["intent"] = decision.selected_intent or goal_plan.get("intent")
                goal_plan["reason"] = decision.reason
                goal_plan.setdefault("safe_to_execute", True)
                return goal_plan

        intent = str(decision.selected_intent or "calm_idle")
        try:
            from modules.agent_core.services.runtime import CompanionPlanAdapter

            adapter = getattr(self, "_companion_plan_adapter", None)
            if adapter is None:
                adapter = CompanionPlanAdapter()
                self._companion_plan_adapter = adapter
            built = adapter.build_for_intent(
                intent,
                goal=decision.selected_goal,
                context={
                    "owner_present": owner_present,
                    "dominant_need": dominant,
                    "recommended_goal": recommended,
                },
                scores=scores,
            )
            built["deferred"] = False
            built["reason"] = decision.reason
            built["intent"] = intent
            if decision.selected_goal is not None:
                built["typed_goal"] = decision.selected_goal.to_dict()
                if isinstance(built.get("typed_plan"), dict):
                    built["typed_plan"] = dict(built["typed_plan"])
                    built["typed_plan"]["goal_id"] = decision.selected_goal.id
            return built
        except Exception as exc:
            logger.warning("build_for_intent failed (%s); calm_idle fallback", exc)
            return self._plan_for(dominant, recommended, scores=scores, owner_present=owner_present, snapshot=snapshot)
