"""Deterministic (+ optional mocked model) companion goal candidate generation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from .schemas import (
    GoalCandidate,
    GoalCandidateSource,
    GoalFormationContext,
    GoalSnapshot,
    GoalStatus,
)

ModelAssistFn = Callable[[GoalFormationContext], List[GoalCandidate]]

# Allowlisted intents for model assist / planning compatibility.
ALLOWED_INTENTS = frozenset(
    {
        "pause_and_observe",
        "settle_or_rest",
        "social_check_in",
        "seek_owner_or_invite",
        "inspect_environment",
        "inspect_sound_source",
        "look_around_and_learn",
        "scan_for_company_then_rest",
        "calm_idle",
        "resume_existing_goal",
    }
)

INTENT_CAPABILITIES: Dict[str, List[str]] = {
    "pause_and_observe": ["expression.event", "motion.freeze", "vision.cheap"],
    "settle_or_rest": ["navigation.rest_corner", "pose.sleepy_idle", "speech.silent"],
    "social_check_in": ["expression.event", "speech.short_prompt", "motion.attend"],
    "seek_owner_or_invite": ["perception.owner_scan", "speech.short_prompt"],
    "inspect_environment": ["vision.cheap", "vision.semantic", "motion.attend"],
    "inspect_sound_source": ["perception.track_object", "vision.cheap"],
    "look_around_and_learn": ["vision.cheap", "motion.look_around", "memory.observe"],
    "scan_for_company_then_rest": ["perception.owner_scan", "pose.sleepy_idle"],
    "calm_idle": ["scheduler.wait", "expression.event"],
    "resume_existing_goal": [],
}


def _strength(context: GoalFormationContext, kind: str) -> float:
    for need in context.needs:
        if need.kind == kind:
            return max(0.0, min(1.0, float(need.strength)))
    return max(0.0, min(1.0, float(context.scores.get(kind) or 0.0)))


def _novelty(context: GoalFormationContext) -> float:
    perception = context.perception or {}
    for key in ("novelty", "scene_novelty", "change_score"):
        if key in perception:
            try:
                return max(0.0, min(1.0, float(perception.get(key))))
            except (TypeError, ValueError):
                pass
    importance = perception.get("importance") or context.metadata.get("scene_importance")
    try:
        return max(0.0, min(1.0, float(importance or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _hazards(context: GoalFormationContext) -> bool:
    perception = context.perception or {}
    hazards = perception.get("hazards") or context.metadata.get("hazards") or []
    if isinstance(hazards, list) and hazards:
        return True
    return _strength(context, "safety") >= 0.7 or context.dominant_need == "safety"


def _sound_interest(context: GoalFormationContext) -> bool:
    if context.recommended_goal == "inspect_sound_source":
        return True
    perception = context.perception or {}
    audio = perception.get("audio_context") if isinstance(perception.get("audio_context"), dict) else {}
    return bool(perception.get("sound_recent") or audio.get("sound_recent") or audio.get("interesting"))


class GoalCandidateGenerator:
    """Propose bounded GoalCandidates. Never authorizes or executes."""

    def __init__(
        self,
        *,
        cfg: Optional[Dict[str, Any]] = None,
        model_assist_fn: Optional[ModelAssistFn] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.max_candidates = max(1, int(raw.get("max_candidates", 6)))
        self.model_assist = bool(raw.get("model_assist", False))
        self.model_assist_fn = model_assist_fn

    def generate(self, context: GoalFormationContext) -> List[GoalCandidate]:
        candidates: List[GoalCandidate] = []
        candidates.extend(self._resume_candidate(context))
        candidates.extend(self._safety_candidate(context))
        candidates.extend(self._social_candidates(context))
        candidates.extend(self._environment_candidates(context))
        candidates.extend(self._rest_candidate(context))
        candidates.extend(self._idle_candidate(context))

        if self.model_assist and self.model_assist_fn is not None:
            try:
                proposed = self.model_assist_fn(context) or []
            except Exception:
                proposed = []
            for item in proposed:
                if not isinstance(item, GoalCandidate):
                    continue
                if item.intent not in ALLOWED_INTENTS:
                    continue
                item.source = GoalCandidateSource.MODEL
                if not item.required_capabilities:
                    item.required_capabilities = list(INTENT_CAPABILITIES.get(item.intent) or [])
                candidates.append(item)

        # De-dupe by intent, keep highest utility+urgency
        best: Dict[str, GoalCandidate] = {}
        for cand in candidates:
            prior = best.get(cand.intent)
            score = cand.expected_utility + cand.urgency
            if prior is None or score > (prior.expected_utility + prior.urgency):
                best[cand.intent] = cand
        ordered = sorted(
            best.values(),
            key=lambda c: (c.urgency, c.expected_utility, c.novelty),
            reverse=True,
        )
        return ordered[: self.max_candidates]

    def _resume_candidate(self, context: GoalFormationContext) -> List[GoalCandidate]:
        snap = context.active_goal
        if snap is None:
            return []
        if snap.status not in {GoalStatus.ACTIVE, GoalStatus.WAITING, GoalStatus.REPLANNING}:
            return []
        if snap.expires_at is not None and float(snap.expires_at) <= float(context.now):
            return []
        if not snap.has_executable_work() and snap.status != GoalStatus.REPLANNING:
            return []
        intent = str((snap.params or {}).get("intent") or (snap.goal_plan or {}).get("intent") or "resume_existing_goal")
        if intent not in ALLOWED_INTENTS:
            intent = "resume_existing_goal"
        return [
            GoalCandidate(
                intent=intent if intent != "resume_existing_goal" else "resume_existing_goal",
                description="Continue active companion intention",
                reason="valid_active_or_waiting_goal",
                source=GoalCandidateSource.RESUME,
                expected_utility=0.7,
                urgency=0.55,
                confidence=0.9,
                novelty=0.1,
                estimated_cost=0.2,
                estimated_risk=0.2,
                deferable=False,
                continuity_of_goal_id=snap.goal_id,
                metadata={"resume": True, "goal_id": snap.goal_id},
            )
        ]

    def _safety_candidate(self, context: GoalFormationContext) -> List[GoalCandidate]:
        if not _hazards(context):
            return []
        return [
            GoalCandidate(
                intent="pause_and_observe",
                description="Pause and observe due to safety signal",
                reason="safety_or_hazard",
                source=GoalCandidateSource.RULES,
                need_ids=[n.id for n in context.needs if n.kind == "safety"],
                required_capabilities=list(INTENT_CAPABILITIES["pause_and_observe"]),
                expected_utility=0.9,
                urgency=0.95,
                confidence=0.85,
                novelty=0.4,
                estimated_cost=0.15,
                estimated_risk=0.1,
                deferable=False,
            )
        ]

    def _social_candidates(self, context: GoalFormationContext) -> List[GoalCandidate]:
        social = _strength(context, "social")
        if social < 0.35 and context.dominant_need != "social":
            return []
        if context.owner_present:
            return [
                GoalCandidate(
                    intent="social_check_in",
                    description="Engage owner socially",
                    reason="owner_present_social_need",
                    source=GoalCandidateSource.RULES,
                    need_ids=[n.id for n in context.needs if n.kind == "social"],
                    required_capabilities=list(INTENT_CAPABILITIES["social_check_in"]),
                    expected_utility=0.55 + 0.3 * social,
                    urgency=0.35 + 0.3 * social,
                    confidence=0.7,
                    novelty=0.35,
                    estimated_cost=0.35,
                    estimated_risk=0.25,
                )
            ]
        return [
            GoalCandidate(
                intent="seek_owner_or_invite",
                description="Seek owner or invite interaction",
                reason="social_need_owner_absent",
                source=GoalCandidateSource.RULES,
                need_ids=[n.id for n in context.needs if n.kind == "social"],
                required_capabilities=list(INTENT_CAPABILITIES["seek_owner_or_invite"]),
                expected_utility=0.45 + 0.25 * social,
                urgency=0.3 + 0.25 * social,
                confidence=0.6,
                novelty=0.4,
                estimated_cost=0.4,
                estimated_risk=0.3,
            )
        ]

    def _environment_candidates(self, context: GoalFormationContext) -> List[GoalCandidate]:
        out: List[GoalCandidate] = []
        curiosity = max(_strength(context, "curiosity"), _strength(context, "exploration"))
        novelty = _novelty(context)
        if _sound_interest(context):
            out.append(
                GoalCandidate(
                    intent="inspect_sound_source",
                    description="Inspect interesting sound",
                    reason="sound_interest",
                    source=GoalCandidateSource.RULES,
                    required_capabilities=list(INTENT_CAPABILITIES["inspect_sound_source"]),
                    expected_utility=0.55,
                    urgency=0.5,
                    confidence=0.65,
                    novelty=max(0.5, novelty),
                    estimated_cost=0.35,
                    estimated_risk=0.25,
                )
            )
        if curiosity >= 0.35 or novelty >= 0.45 or context.dominant_need in {"curiosity", "exploration"}:
            intent = "look_around_and_learn" if context.dominant_need == "exploration" else "inspect_environment"
            out.append(
                GoalCandidate(
                    intent=intent,
                    description="Inspect environment from curiosity/novelty",
                    reason="curiosity_or_scene_change",
                    source=GoalCandidateSource.RULES,
                    need_ids=[n.id for n in context.needs if n.kind in {"curiosity", "exploration"}],
                    required_capabilities=list(INTENT_CAPABILITIES[intent]),
                    expected_utility=0.45 + 0.4 * curiosity + 0.25 * novelty,
                    urgency=0.25 + 0.3 * novelty,
                    confidence=0.65,
                    novelty=novelty,
                    estimated_cost=0.35,
                    estimated_risk=0.2,
                )
            )
        boredom = _strength(context, "boredom")
        if boredom >= 0.45 or context.dominant_need == "boredom":
            out.append(
                GoalCandidate(
                    intent="scan_for_company_then_rest",
                    description="Scan for company then settle",
                    reason="boredom",
                    source=GoalCandidateSource.RULES,
                    required_capabilities=list(INTENT_CAPABILITIES["scan_for_company_then_rest"]),
                    expected_utility=0.35 + 0.25 * boredom,
                    urgency=0.25,
                    confidence=0.55,
                    novelty=0.3,
                    estimated_cost=0.3,
                    estimated_risk=0.2,
                )
            )
        return out

    def _rest_candidate(self, context: GoalFormationContext) -> List[GoalCandidate]:
        rest = _strength(context, "rest")
        energy = _strength(context, "energy")
        if rest < 0.4 and energy > 0.35 and context.dominant_need != "rest":
            return []
        return [
            GoalCandidate(
                intent="settle_or_rest",
                description="Settle in a safe place",
                reason="rest_or_low_energy",
                source=GoalCandidateSource.RULES,
                need_ids=[n.id for n in context.needs if n.kind in {"rest", "energy"}],
                required_capabilities=list(INTENT_CAPABILITIES["settle_or_rest"]),
                expected_utility=0.4 + 0.3 * rest,
                urgency=0.2 + 0.2 * rest,
                confidence=0.7,
                novelty=0.15,
                estimated_cost=0.35,
                estimated_risk=0.2,
            )
        ]

    def _idle_candidate(self, context: GoalFormationContext) -> List[GoalCandidate]:
        # Always available as a weak option; evaluator often defers it.
        return [
            GoalCandidate(
                intent="calm_idle",
                description="Remain calm / low activity",
                reason="balanced_or_weak_needs",
                source=GoalCandidateSource.FALLBACK,
                required_capabilities=list(INTENT_CAPABILITIES["calm_idle"]),
                expected_utility=0.2,
                urgency=0.05,
                confidence=0.8,
                novelty=0.05,
                estimated_cost=0.05,
                estimated_risk=0.05,
                deferable=True,
            )
        ]


__all__ = ["GoalCandidateGenerator", "ModelAssistFn", "ALLOWED_INTENTS", "INTENT_CAPABILITIES"]
