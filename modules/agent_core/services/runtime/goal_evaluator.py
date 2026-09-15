"""Rank and suppress companion goal candidates."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from .schemas import GoalCandidate, GoalFormationContext, GoalFormationDisposition, GoalStatus

# WAITING goals with these intents may be displaced by owner-return social.
LOW_URGENCY_INTERRUPTIBLE = frozenset(
    {
        "inspect_environment",
        "look_around_and_learn",
        "calm_idle",
        "scan_for_company_then_rest",
        "resume_existing_goal",
    }
)


class GoalEvaluator:
    """Lexicographic / feature-based ranking with continuity, outcomes, and soft interrupt."""

    def __init__(self, *, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.min_activation = float(raw.get("min_activation_score", 0.30))
        self.continuity_bonus = float(raw.get("continuity_bonus", 0.20))
        self.repetition_window_s = float(raw.get("repetition_window_s", 900))
        self.max_same_goal_repeats = max(1, int(raw.get("max_same_goal_repeats", 2)))
        self.outcome_window_s = float(raw.get("outcome_window_s", 900))
        self.outcome_failure_penalty = float(raw.get("outcome_failure_penalty", 0.35))
        self.outcome_success_bonus = float(raw.get("outcome_success_bonus", 0.15))
        self.allow_soft_interrupt = bool(raw.get("allow_soft_interrupt", True))
        self.soft_interrupt_social_min = float(raw.get("soft_interrupt_social_min", 0.55))
        self.history: Deque[Dict[str, Any]] = deque(maxlen=32)
        self.outcomes: Deque[Dict[str, Any]] = deque(maxlen=24)

    def record_selection(self, intent: str, *, outcome: str = "selected", now: Optional[float] = None) -> None:
        self.history.append(
            {
                "intent": str(intent),
                "outcome": str(outcome),
                "timestamp": float(now if now is not None else time.time()),
            }
        )

    def record_outcome(self, intent: str, *, succeeded: bool, now: Optional[float] = None) -> None:
        """Bounded intent-keyed outcome for ranking (Batch 6a)."""
        intent_key = str(intent or "").strip()
        if not intent_key:
            return
        self.outcomes.append(
            {
                "intent": intent_key,
                "succeeded": bool(succeeded),
                "timestamp": float(now if now is not None else time.time()),
            }
        )
        self.record_selection(
            intent_key,
            outcome="success" if succeeded else "failure",
            now=now,
        )

    def seed_history(self, items: List[Dict[str, Any]]) -> None:
        self.history.clear()
        for item in items[-24:]:
            if isinstance(item, dict) and item.get("intent"):
                self.history.append(dict(item))

    def seed_outcomes(self, items: List[Dict[str, Any]]) -> None:
        self.outcomes.clear()
        for item in items[-24:]:
            if not isinstance(item, dict) or not item.get("intent"):
                continue
            if "succeeded" in item:
                self.outcomes.append(
                    {
                        "intent": str(item.get("intent")),
                        "succeeded": bool(item.get("succeeded")),
                        "timestamp": float(item.get("timestamp") or time.time()),
                    }
                )

    def evaluate(
        self,
        candidates: List[GoalCandidate],
        context: GoalFormationContext,
    ) -> Tuple[Optional[GoalCandidate], GoalFormationDisposition, str, List[Dict[str, str]], Dict[str, Any]]:
        rejected: List[Dict[str, str]] = []
        scored: List[Tuple[float, GoalCandidate, Dict[str, Any]]] = []

        for cand in candidates:
            rep = self._repetition_penalty(cand.intent, context.now)
            if rep >= 1.0 and cand.source.value != "resume":
                rejected.append({"intent": cand.intent, "reason": "goal_suppressed_repetition"})
                continue
            features = self._features(cand, context, rep)
            score = features["score"]
            scored.append((score, cand, features))

        if not scored:
            return None, GoalFormationDisposition.DEFER, "no_viable_candidates", rejected, {}

        scored.sort(key=lambda item: item[0], reverse=True)

        # 1) Urgent non-deferable safety
        for score, cand, features in scored:
            if cand.intent == "pause_and_observe" and cand.urgency >= 0.8:
                return cand, GoalFormationDisposition.SELECT, "urgent_safety", rejected, features

        # 2) Continuity / resume — unless soft interrupt applies
        soft = self.soft_interrupt_applies(context)
        if soft:
            # Drop resume/continuity candidates so they cannot win as ranked_best.
            filtered: List[Tuple[float, GoalCandidate, Dict[str, Any]]] = []
            for score, cand, features in scored:
                if cand.source.value == "resume" or cand.continuity_of_goal_id:
                    rejected.append(
                        {
                            "intent": cand.intent,
                            "reason": "soft_interrupt_owner_social",
                        }
                    )
                    continue
                filtered.append((score, cand, features))
            scored = filtered
            if not scored:
                return None, GoalFormationDisposition.DEFER, "soft_interrupt_no_alternative", rejected, {}
        else:
            for score, cand, features in scored:
                if cand.source.value == "resume" or cand.continuity_of_goal_id:
                    return cand, GoalFormationDisposition.RESUME, "continuity_preference", rejected, features

        best_score, best, best_features = scored[0]
        if best.intent == "calm_idle" and best_score < self.min_activation + 0.15:
            return None, GoalFormationDisposition.DEFER, "weak_idle_below_activation", rejected, best_features
        if best_score < self.min_activation:
            rejected.append({"intent": best.intent, "reason": "below_activation_threshold"})
            return None, GoalFormationDisposition.DEFER, "all_candidates_below_activation", rejected, best_features

        reason = "ranked_best_candidate"
        if soft and best.intent in {"social_check_in", "seek_owner_or_invite"}:
            reason = "soft_interrupt_owner_social"
        return best, GoalFormationDisposition.SELECT, reason, rejected, best_features

    def soft_interrupt_applies(self, context: GoalFormationContext) -> bool:
        """Owner-return / high-social may displace low-urgency WAITING foreground."""
        if not self.allow_soft_interrupt:
            return False
        active = context.active_goal
        if active is None or active.status != GoalStatus.WAITING:
            return False
        if not active.has_executable_work():
            return False
        intent = str(
            (active.params or {}).get("intent")
            or (active.goal_plan or {}).get("intent")
            or ""
        ).strip()
        if intent and intent not in LOW_URGENCY_INTERRUPTIBLE:
            return False
        if not context.owner_present:
            return False
        social = 0.0
        for need in context.needs:
            if need.kind == "social":
                social = max(social, float(need.strength))
        social = max(social, float(context.scores.get("social") or 0.0))
        if context.dominant_need == "social":
            social = max(social, self.soft_interrupt_social_min)
        return social >= self.soft_interrupt_social_min

    def _features(self, cand: GoalCandidate, context: GoalFormationContext, rep_penalty: float) -> Dict[str, Any]:
        continuity = self.continuity_bonus if (cand.source.value == "resume" or cand.continuity_of_goal_id) else 0.0
        outcome_adj = self._outcome_adjustment(cand.intent, context.now)
        score = (
            float(cand.expected_utility)
            + float(cand.urgency)
            + 0.5 * float(cand.novelty)
            + continuity
            + outcome_adj
            - float(cand.estimated_cost)
            - float(cand.estimated_risk)
            - rep_penalty
        )
        return {
            "score": round(score, 4),
            "utility": round(float(cand.expected_utility), 3),
            "urgency": round(float(cand.urgency), 3),
            "novelty": round(float(cand.novelty), 3),
            "cost": round(float(cand.estimated_cost), 3),
            "risk": round(float(cand.estimated_risk), 3),
            "continuity_bonus": continuity,
            "repetition_penalty": round(rep_penalty, 3),
            "outcome_adjustment": round(outcome_adj, 3),
        }

    def _outcome_adjustment(self, intent: str, now: float) -> float:
        cutoff = float(now) - self.outcome_window_s
        recent = [
            o
            for o in self.outcomes
            if o.get("intent") == intent and float(o.get("timestamp") or 0) >= cutoff
        ]
        if not recent:
            return 0.0
        failures = sum(1 for o in recent if not o.get("succeeded"))
        successes = sum(1 for o in recent if o.get("succeeded"))
        adj = 0.0
        adj -= min(0.7, failures * self.outcome_failure_penalty)
        adj += min(0.3, successes * self.outcome_success_bonus)
        return adj

    def _repetition_penalty(self, intent: str, now: float) -> float:
        cutoff = float(now) - self.repetition_window_s
        # Only selection events count toward repetition; success/failure outcomes do not.
        recent = [
            h
            for h in self.history
            if h.get("intent") == intent
            and float(h.get("timestamp") or 0) >= cutoff
            and str(h.get("outcome") or "selected") == "selected"
        ]
        if len(recent) >= self.max_same_goal_repeats:
            return 1.0
        if len(recent) == self.max_same_goal_repeats - 1:
            return 0.45
        if recent:
            return 0.2
        return 0.0


__all__ = ["GoalEvaluator", "LOW_URGENCY_INTERRUPTIBLE"]
