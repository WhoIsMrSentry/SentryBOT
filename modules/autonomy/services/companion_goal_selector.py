from __future__ import annotations

import time
from typing import Any, Dict, Optional

from modules.autonomy.services.pet_companion_core import PetCompanionCore

PET_COMPANION_GOAL_SELECTOR_INTEGRATION_CONTRACT = True
PET_COMPANION_GOAL_SELECTOR_INTEGRATION_ROLE = "pet_core_side_channel_for_goal_selector"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class CompanionGoalSelector:
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
        scores = _as_dict(snap.get("scores"))

        plan = self._plan_for(dominant, recommended, scores=scores, owner_present=owner_present)
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
        return out


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

    def _plan_for(self, dominant: str, recommended: str, *, scores: Dict[str, Any], owner_present: bool) -> Dict[str, Any]:
        if dominant == "safety":
            return {
                "behavior": "pause_and_observe",
                "priority": "critical",
                "expression_event": "needs.safety",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.safety"},
                    {"type": "motion", "name": "freeze", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "safety"},
                ],
            }
        if recommended == "rest_in_safe_place" or dominant == "rest":
            return {
                "behavior": "rest_in_safe_place",
                "priority": "low",
                "expression_event": "needs.rest",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.rest"},
                    {"type": "navigation", "name": "rest_corner", "risk": "low"},
                    {"type": "pose", "name": "sleepy_idle", "risk": "low"},
                    {"type": "speech", "mode": "silent"},
                ],
            }
        if dominant == "social":
            return {
                "behavior": "seek_owner_or_invite_interaction" if not owner_present else "engage_owner",
                "priority": "normal",
                "expression_event": "needs.social",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.social"},
                    {"type": "perception", "name": "owner_scan", "risk": "low"},
                    {"type": "speech", "mode": "short_prompt", "template": "social_invite"},
                ],
            }
        if dominant == "exploration":
            return {
                "behavior": "look_around_and_learn",
                "priority": "normal",
                "expression_event": "needs.exploration",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.exploration"},
                    {"type": "vision", "mode": "cheap", "reason": "exploration"},
                    {"type": "motion", "name": "look_around", "risk": "low"},
                ],
            }
        if recommended == "look_for_company_or_rest" or dominant == "boredom":
            return {
                "behavior": "scan_for_company_then_rest",
                "priority": "normal",
                "expression_event": "needs.boredom",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.boredom"},
                    {"type": "motion", "name": "stretch_or_scan", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "boredom"},
                    {"type": "perception", "name": "track_person", "label": "person", "strategy": "center", "risk": "low"},
                    {"type": "memory", "name": "observe", "kind": "episode", "summary": "Robot was bored and scanned for company.", "risk": "none"},
                ],
            }
        if recommended == "inspect_sound_source":
            return {
                "behavior": "inspect_sound_source",
                "priority": "high",
                "expression_event": "needs.sound_attention",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.sound_attention"},
                    {"type": "motion", "name": "attend", "risk": "low"},
                    {"type": "perception", "name": "track_person", "label": "person", "strategy": "center", "risk": "low"},
                    {"type": "vision", "mode": "cheap", "reason": "sound_interrupt"},
                ],
            }
        if dominant == "curiosity":
            return {
                "behavior": "inspect_environment_and_learn",
                "priority": "normal",
                "expression_event": "needs.curiosity",
                "safe_to_execute": True,
                "actions": [
                    {"type": "expression", "event": "needs.curiosity"},
                    {"type": "vision", "mode": "cheap", "reason": "curiosity"},
                    {"type": "vision", "mode": "semantic", "reason": "curiosity_unknown"},
                    {"type": "motion", "name": "attend", "risk": "low"},
                ],
            }
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
