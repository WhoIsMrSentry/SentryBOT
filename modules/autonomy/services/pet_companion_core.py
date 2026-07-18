from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any, Dict, Mapping, Optional

PET_COMPANION_CORE_CONTRACT = True
PET_COMPANION_CORE_ROLE = "personality_bond_routine_to_semantic_pet_behavior"
PET_COMPANION_CORE_HARDWARE_SAFE = True


DEFAULT_PROFILE = {
    "name": "sentry",
    "traits": {
        "curiosity": 0.72,
        "sociability": 0.68,
        "calmness": 0.58,
        "playfulness": 0.62,
        "protectiveness": 0.70,
        "independence": 0.45,
    },
    "style": {
        "speech": "short_warm",
        "motion": "soft_reactive",
        "expression": "alive_subtle",
    },
}


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class PersonalityProfile:
    name: str = "sentry"
    curiosity: float = 0.72
    sociability: float = 0.68
    calmness: float = 0.58
    playfulness: float = 0.62
    protectiveness: float = 0.70
    independence: float = 0.45
    speech_style: str = "short_warm"
    motion_style: str = "soft_reactive"
    expression_style: str = "alive_subtle"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PersonalityProfile":
        traits = _mapping(data.get("traits"))
        style = _mapping(data.get("style"))
        return cls(
            name=str(data.get("name", "sentry")),
            curiosity=_clamp(traits.get("curiosity", DEFAULT_PROFILE["traits"]["curiosity"])),
            sociability=_clamp(traits.get("sociability", DEFAULT_PROFILE["traits"]["sociability"])),
            calmness=_clamp(traits.get("calmness", DEFAULT_PROFILE["traits"]["calmness"])),
            playfulness=_clamp(traits.get("playfulness", DEFAULT_PROFILE["traits"]["playfulness"])),
            protectiveness=_clamp(traits.get("protectiveness", DEFAULT_PROFILE["traits"]["protectiveness"])),
            independence=_clamp(traits.get("independence", DEFAULT_PROFILE["traits"]["independence"])),
            speech_style=str(style.get("speech", DEFAULT_PROFILE["style"]["speech"])),
            motion_style=str(style.get("motion", DEFAULT_PROFILE["style"]["motion"])),
            expression_style=str(style.get("expression", DEFAULT_PROFILE["style"]["expression"])),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "traits": {
                "curiosity": self.curiosity,
                "sociability": self.sociability,
                "calmness": self.calmness,
                "playfulness": self.playfulness,
                "protectiveness": self.protectiveness,
                "independence": self.independence,
            },
            "style": {
                "speech": self.speech_style,
                "motion": self.motion_style,
                "expression": self.expression_style,
            },
        }


@dataclass(frozen=True)
class PetCompanionDecision:
    intent: str
    reason: str
    score: float
    expression_hint: str
    motion_hint: str
    speech_hint: str
    goal_hints: list[str] = field(default_factory=list)
    needs_bias: Dict[str, float] = field(default_factory=dict)
    memory_tags: list[str] = field(default_factory=list)
    safety: Dict[str, bool] = field(default_factory=dict)
    status_only: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "reason": self.reason,
            "score": round(float(self.score), 3),
            "expression_hint": self.expression_hint,
            "motion_hint": self.motion_hint,
            "speech_hint": self.speech_hint,
            "goal_hints": list(self.goal_hints),
            "needs_bias": dict(self.needs_bias),
            "memory_tags": list(self.memory_tags),
            "safety": dict(self.safety),
            "status_only": self.status_only,
        }


class PetCompanionCore:
    """Semantic pet-like behavior selector for autonomy.

    This is real autonomy logic, not a hardware adapter. It turns needs,
    relationship/bond state, routine energy, and perception hints into a
    pet-like semantic intent. Hardware execution remains behind existing
    autonomy goal/capability/safety gates.
    """

    def __init__(self, profile: Optional[PersonalityProfile] = None) -> None:
        self.profile = profile or PersonalityProfile.from_mapping(DEFAULT_PROFILE)

    def decide(self, context: Optional[Mapping[str, Any]] = None) -> PetCompanionDecision:
        data = _mapping(context)
        needs = _mapping(data.get("needs"))
        bond = _mapping(data.get("bond"))
        routine = _mapping(data.get("routine"))
        perception = _mapping(data.get("perception"))

        safety_need = _clamp(needs.get("safety", 0.0))
        energy = _clamp(routine.get("energy", needs.get("energy", 0.7)), default=0.7)
        boredom = _clamp(needs.get("boredom", 0.0))
        curiosity = _clamp(needs.get("curiosity", 0.0))
        social = _clamp(needs.get("social", 0.0))
        owner_present = bool(perception.get("owner_present", perception.get("person_present", False)))
        owner_speaking = bool(perception.get("owner_speaking", False))
        trust = _clamp(bond.get("trust", 0.35), default=0.35)
        affection = _clamp(bond.get("affection", 0.35), default=0.35)

        candidates = {
            "safe_observe": safety_need * (0.8 + self.profile.protectiveness * 0.5),
            "rest_nearby": (1.0 - energy) * (0.7 + self.profile.calmness * 0.4),
            "attend_owner": (social + affection * 0.5 + trust * 0.3 + (0.35 if owner_present else 0.0)) * self.profile.sociability,
            "listen_owner": (0.6 if owner_speaking else 0.0) + social * 0.4,
            "curious_inspect": (curiosity * 0.7 + boredom * 0.35) * self.profile.curiosity,
            "playful_ping": (boredom * 0.65 + energy * 0.25) * self.profile.playfulness,
            "calm_idle": self.profile.calmness * 0.35 + self.profile.independence * 0.25,
        }

        if safety_need >= 0.55:
            intent = "safe_observe"
        elif energy <= 0.25:
            intent = "rest_nearby"
        else:
            intent = max(candidates, key=candidates.get)

        return self._decision_for(intent, candidates[intent], owner_present=owner_present, owner_speaking=owner_speaking)

    def _decision_for(self, intent: str, score: float, *, owner_present: bool, owner_speaking: bool) -> PetCompanionDecision:
        safety = {
            "hardware_enabled": False,
            "motion_started": False,
            "audio_started": False,
            "camera_started": False,
            "vlm_started": False,
            "semantic_only": True,
        }

        if intent == "safe_observe":
            return PetCompanionDecision(
                intent=intent,
                reason="safety_need_dominant",
                score=score,
                expression_hint="alert_soft",
                motion_hint="freeze_or_slow_scan",
                speech_hint="silent_or_short_check",
                goal_hints=["prefer_safe_observation", "avoid_motion_until_clear"],
                needs_bias={"safety": 0.7},
                memory_tags=["safety_context"],
                safety=safety,
            )

        if intent == "rest_nearby":
            return PetCompanionDecision(
                intent=intent,
                reason="low_energy_or_rest_routine",
                score=score,
                expression_hint="sleepy_calm",
                motion_hint="settle_near_owner",
                speech_hint="minimal",
                goal_hints=["rest", "stay_available"],
                needs_bias={"energy_recovery": 0.5},
                memory_tags=["routine_rest"],
                safety=safety,
            )

        if intent == "attend_owner":
            return PetCompanionDecision(
                intent=intent,
                reason="bond_social_owner_presence",
                score=score,
                expression_hint="happy_attentive" if owner_present else "searching_soft",
                motion_hint="orient_to_owner",
                speech_hint=self.profile.speech_style,
                goal_hints=["orient_to_owner", "offer_presence", "update_bond_memory"],
                needs_bias={"social": 0.35, "bond": 0.25},
                memory_tags=["owner_interaction"],
                safety=safety,
            )

        if intent == "listen_owner":
            return PetCompanionDecision(
                intent=intent,
                reason="owner_speaking_or_audio_attention",
                score=score,
                expression_hint="listening",
                motion_hint="hold_still_attention",
                speech_hint="do_not_interrupt",
                goal_hints=["listen", "avoid_talking_over_owner"],
                needs_bias={"attention": 0.4},
                memory_tags=["audio_attention"],
                safety=safety,
            )

        if intent == "curious_inspect":
            return PetCompanionDecision(
                intent=intent,
                reason="curiosity_or_boredom",
                score=score,
                expression_hint="curious",
                motion_hint="small_head_tilt_or_scan",
                speech_hint="curious_short",
                goal_hints=["inspect_interesting_context", "ask_short_question_if_allowed"],
                needs_bias={"curiosity": 0.4},
                memory_tags=["curiosity_context"],
                safety=safety,
            )

        if intent == "playful_ping":
            return PetCompanionDecision(
                intent=intent,
                reason="boredom_with_enough_energy",
                score=score,
                expression_hint="playful",
                motion_hint="small_bouncy_idle",
                speech_hint="playful_short",
                goal_hints=["invite_interaction", "small_idle_animation"],
                needs_bias={"play": 0.35, "social": 0.15},
                memory_tags=["play_context"],
                safety=safety,
            )

        return PetCompanionDecision(
            intent="calm_idle",
            reason="stable_low_pressure_state",
            score=score,
            expression_hint="calm_alive",
            motion_hint="breathing_idle",
            speech_hint="silent",
            goal_hints=["ambient_presence"],
            needs_bias={"calm": 0.2},
            memory_tags=["ambient_state"],
            safety=safety,
        )


def load_personality_profile(path: str | Path = "config/autonomy/pet_companion_profile.json") -> PersonalityProfile:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return PersonalityProfile.from_mapping(DEFAULT_PROFILE)
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        data = DEFAULT_PROFILE
    return PersonalityProfile.from_mapping(_mapping(data))


def decide_pet_companion_behavior(context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    profile = load_personality_profile()
    return PetCompanionCore(profile).decide(context).as_dict()
