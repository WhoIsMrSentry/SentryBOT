"""Bounded companion goal formation — decides WHAT, never executes."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from .capability_index import CapabilityIndex
from .decision_trace import DecisionTraceStore
from .goal_candidate_generator import GoalCandidateGenerator, ModelAssistFn
from .goal_evaluator import GoalEvaluator
from .goal_policy_gate import GoalPolicyGate, GoalReject
from .goal_store import GoalStore
from .schemas import (
    Goal,
    GoalFormationContext,
    GoalFormationDecision,
    GoalFormationDisposition,
    GoalSnapshot,
    GoalStatus,
    NeedSignal,
    PolicyConstraints,
)


def normalize_need_scores(scores: Dict[str, Any]) -> Dict[str, float]:
    parsed: Dict[str, float] = {}
    for key, value in dict(scores or {}).items():
        try:
            parsed[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    if not parsed:
        return {}
    # CompanionNeedsEngine uses 0–100; LivingNeedsEngine uses 0–1.
    scale = 100.0 if max(parsed.values()) > 1.5 else 1.0
    return {key: max(0.0, min(1.0, value / scale)) for key, value in parsed.items()}


def needs_from_snapshot(snapshot: Dict[str, Any]) -> List[NeedSignal]:
    scores = normalize_need_scores(snapshot.get("scores") or {})
    signals: List[NeedSignal] = []
    for kind, strength in scores.items():
        if kind in {"owner_proximity"}:
            continue
        signals.append(
            NeedSignal(
                kind=str(kind),
                strength=float(strength),
                source="needs_engine",
                metadata={"dominant": str(snapshot.get("dominant_need") or "") == str(kind)},
            )
        )
    dominant = str(snapshot.get("dominant_need") or "").strip().lower()
    if dominant and dominant not in scores:
        signals.append(NeedSignal(kind=dominant, strength=0.6, source="dominant_need"))
    return signals


def context_fingerprint(context: GoalFormationContext) -> str:
    payload = {
        "dominant": context.dominant_need,
        "recommended": context.recommended_goal,
        "owner": context.owner_present,
        "quiet": context.quiet_hours,
        "active": context.active_goal.goal_id if context.active_goal else None,
        "active_status": context.active_goal.status.value if context.active_goal else None,
        "needs": sorted((n.kind, round(n.strength, 2)) for n in context.needs),
        "novelty": round(float((context.perception or {}).get("novelty") or (context.perception or {}).get("importance") or 0), 2),
        "hazards": bool((context.perception or {}).get("hazards")),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


class GoalFormationService:
    """Form one foreground companion intention (or defer) from context."""

    def __init__(
        self,
        *,
        cfg: Optional[Dict[str, Any]] = None,
        capabilities: Optional[CapabilityIndex] = None,
        goal_store: Optional[GoalStore] = None,
        traces: Optional[DecisionTraceStore] = None,
        model_assist_fn: Optional[ModelAssistFn] = None,
    ) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg = raw
        self.enabled = bool(raw.get("enabled", True))
        self.allow_supersede = bool(raw.get("allow_supersede", True))
        self.capabilities = capabilities if capabilities is not None else CapabilityIndex.from_robot_registry()
        self.goal_store = goal_store
        self.traces = traces
        self.generator = GoalCandidateGenerator(cfg=raw, model_assist_fn=model_assist_fn)
        self.evaluator = GoalEvaluator(cfg=raw)
        self.policy_gate = GoalPolicyGate(capabilities=self.capabilities, cfg=raw)
        self._last_decision: Optional[GoalFormationDecision] = None
        self._last_ingested_outcome_ts: float = 0.0

    def form(
        self,
        snapshot: Dict[str, Any],
        *,
        owner_present: bool = False,
        now: Optional[float] = None,
        previous_plan: Optional[Dict[str, Any]] = None,
    ) -> GoalFormationDecision:
        ts = float(now if now is not None else time.time())
        if not self.enabled:
            return GoalFormationDecision(
                disposition=GoalFormationDisposition.DEFER,
                reason="goal_formation_disabled",
                timestamp=ts,
            )

        if self.goal_store is not None:
            self.goal_store.expire_due_goals(now=ts)
            self.goal_store.heal_stuck_replanning(now=ts)
            self.goal_store.prune_terminals(now=ts)

        context = self.build_context(
            snapshot,
            owner_present=owner_present,
            now=ts,
            previous_plan=previous_plan,
        )
        self._ingest_outcome(context)
        fp = context_fingerprint(context)
        context.context_fingerprint = fp

        # Idempotent reuse when context has not materially changed.
        # Soft-interrupt-eligible contexts must re-evaluate (owner/social may displace WAITING).
        if self._can_reuse(context, previous_plan, fp) and not self.evaluator.soft_interrupt_applies(context):
            reused = GoalFormationDecision.from_dict(dict(previous_plan.get("goal_formation") or {}))
            reused.reused = True
            reused.reason = "context_unchanged_reuse"
            reused.context_fingerprint = fp
            reused.timestamp = ts
            self._trace(
                "goal_selected" if reused.disposition != GoalFormationDisposition.DEFER else "goal_deferred",
                reused,
                note="reused",
            )
            self._last_decision = reused
            return reused

        candidates = self.generator.generate(context)
        self._trace_event(
            "goal_candidates_generated",
            reason=f"count={len(candidates)}",
            metadata={"intents": [c.intent for c in candidates], "fingerprint": fp},
        )

        rejected: List[Dict[str, str]] = []
        gated: List = []
        for cand in candidates:
            decision = self.policy_gate.approve(cand, context)
            if isinstance(decision, GoalReject):
                rejected.append({"intent": cand.intent, "reason": ",".join(decision.violations) or decision.reason})
                self._trace_event(
                    "goal_candidate_rejected",
                    reason=decision.reason,
                    metadata={"intent": cand.intent, "violations": decision.violations},
                )
                continue
            gated.append(cand)

        selected, disposition, reason, eval_rejected, features = self.evaluator.evaluate(gated, context)
        rejected.extend(eval_rejected)

        # Narrow supersede:
        # - safety always
        # - soft interrupt: owner-return/high-social displacing low-urgency WAITING
        superseded_id = None
        active = context.active_goal
        soft_interrupt = (
            selected is not None
            and disposition == GoalFormationDisposition.SELECT
            and reason == "soft_interrupt_owner_social"
            and active is not None
            and active.status == GoalStatus.WAITING
            and active.has_executable_work()
            and self.allow_supersede
        )
        safety_supersede = (
            selected is not None
            and disposition == GoalFormationDisposition.SELECT
            and selected.intent == "pause_and_observe"
            and active is not None
            and active.status in {GoalStatus.ACTIVE, GoalStatus.WAITING, GoalStatus.REPLANNING}
            and active.has_executable_work()
            and self.allow_supersede
        )
        if soft_interrupt or safety_supersede:
            disposition = GoalFormationDisposition.SUPERSEDE
            superseded_id = active.goal_id
            if self.goal_store is not None:
                self.goal_store.mark_status(active.goal_id, GoalStatus.SUPERSEDED)
            self._trace_event(
                "goal_superseded",
                reason="soft_interrupt_owner_social" if soft_interrupt else "urgent_safety",
                metadata={
                    "old_goal_id": superseded_id,
                    "new_intent": selected.intent,
                    "soft_interrupt": bool(soft_interrupt),
                },
            )

        if selected is None or disposition == GoalFormationDisposition.DEFER:
            decision = GoalFormationDecision(
                disposition=GoalFormationDisposition.DEFER,
                reason=reason or "defer",
                rejected=rejected,
                candidates_considered=[c.to_dict() for c in candidates],
                features=features,
                context_fingerprint=fp,
                timestamp=ts,
            )
            self._trace("goal_deferred", decision)
            self._last_decision = decision
            return decision

        if disposition == GoalFormationDisposition.RESUME and active is not None:
            goal = Goal(
                id=active.goal_id,
                objective=active.objective or selected.intent,
                status=GoalStatus.ACTIVE,
                metadata={
                    "intent": selected.intent,
                    "source": selected.source.value,
                    "formation_reason": reason,
                    "resume": True,
                },
            )
            decision = GoalFormationDecision(
                disposition=GoalFormationDisposition.RESUME,
                reason=reason,
                selected_intent=str((active.params or {}).get("intent") or selected.intent),
                selected_goal=goal,
                selected_candidate=selected,
                rejected=rejected,
                candidates_considered=[c.to_dict() for c in candidates],
                features=features,
                context_fingerprint=fp,
                timestamp=ts,
                metadata={"goal_plan": active.goal_plan},
            )
            self._trace("goal_selected", decision, note="resume")
            self.evaluator.record_selection(decision.selected_intent or "resume_existing_goal", now=ts)
            self._last_decision = decision
            return decision

        goal = Goal(
            id=f"goal_{selected.intent}_{int(ts)}",
            objective=selected.description or selected.intent,
            status=GoalStatus.PENDING,
            priority=min(1.0, float(selected.urgency) * 0.5 + float(selected.expected_utility) * 0.5),
            metadata={
                "intent": selected.intent,
                "source": selected.source.value,
                "formation_reason": reason,
                "features": features,
            },
        )
        decision = GoalFormationDecision(
            disposition=disposition,
            reason=reason,
            selected_intent=selected.intent,
            selected_goal=goal,
            selected_candidate=selected,
            rejected=rejected,
            candidates_considered=[c.to_dict() for c in candidates],
            features=features,
            superseded_goal_id=superseded_id,
            context_fingerprint=fp,
            timestamp=ts,
        )
        self._trace("goal_selected", decision)
        self.evaluator.record_selection(selected.intent, now=ts)
        self._last_decision = decision
        return decision

    def build_context(
        self,
        snapshot: Dict[str, Any],
        *,
        owner_present: bool,
        now: float,
        previous_plan: Optional[Dict[str, Any]] = None,
    ) -> GoalFormationContext:
        scores = normalize_need_scores(snapshot.get("scores") or {})
        perception = dict(snapshot.get("perception") or {})
        if snapshot.get("scene") and isinstance(snapshot.get("scene"), dict):
            perception.setdefault("hazards", snapshot["scene"].get("hazards"))
            perception.setdefault("importance", snapshot["scene"].get("importance"))
            if snapshot["scene"].get("audio_context"):
                perception.setdefault("audio_context", snapshot["scene"].get("audio_context"))

        routines = snapshot.get("routines") if isinstance(snapshot.get("routines"), dict) else {}
        quiet = bool(routines.get("quiet_time") or snapshot.get("quiet_hours"))
        prefs = snapshot.get("preferences") if isinstance(snapshot.get("preferences"), dict) else {}
        if prefs.get("quiet_mode"):
            quiet = True

        available = list(self.capabilities.describe().get("registry_capabilities") or [])
        health = snapshot.get("capability_health") if isinstance(snapshot.get("capability_health"), dict) else {}
        if isinstance(health.get("capabilities"), list):
            available = [str(c) for c in health.get("capabilities")]

        active = None
        if self.goal_store is not None:
            active = self.goal_store.active_or_waiting(now=now)

        recent = list(self.evaluator.history)
        outcome = snapshot.get("companion_outcome") or snapshot.get("last_outcome")
        if isinstance(outcome, dict):
            # Keep evaluator history warm from outcomes when present
            intent = str(outcome.get("intent") or outcome.get("behavior") or "")
            if intent:
                recent = recent + [{"intent": intent, "timestamp": float(outcome.get("timestamp") or now), "outcome": "completed"}]

        return GoalFormationContext(
            needs=needs_from_snapshot(snapshot),
            active_goal=active,
            recent_goals=recent[-12:],
            recent_outcome=outcome if isinstance(outcome, dict) else None,
            available_capabilities=available,
            owner_present=bool(owner_present),
            quiet_hours=quiet,
            perception=perception,
            mood=dict(snapshot.get("mood") or snapshot.get("semantic_state") or {}),
            memory_hints=list(snapshot.get("memory_hints") or []),
            policy_constraints=PolicyConstraints(
                owner_present=bool(owner_present),
                quiet_hours=quiet,
                risk_ceiling=str(self.cfg.get("risk_ceiling") or "medium"),
            ),
            budget=dict(snapshot.get("budget") or {}),
            dominant_need=str(snapshot.get("dominant_need") or "balance"),
            recommended_goal=str(snapshot.get("recommended_goal") or "calm_idle"),
            scores=scores,
            trigger="think_tick",
            previous_decision=(previous_plan or {}).get("goal_formation") if isinstance(previous_plan, dict) else None,
            now=now,
            metadata={"preferences": prefs, "hazards": perception.get("hazards")},
        )

    def _ingest_outcome(self, context: GoalFormationContext) -> None:
        outcome = context.recent_outcome
        if not isinstance(outcome, dict):
            return
        ts = float(outcome.get("timestamp") or 0.0)
        if ts and ts <= self._last_ingested_outcome_ts:
            return
        intent = str(
            outcome.get("intent")
            or outcome.get("selected_intent")
            or outcome.get("behavior")
            or ""
        ).strip()
        if not intent:
            return
        if "succeeded" not in outcome:
            return
        self.evaluator.record_outcome(intent, succeeded=bool(outcome.get("succeeded")), now=ts or context.now)
        self._last_ingested_outcome_ts = ts or float(context.now)

    def _can_reuse(
        self,
        context: GoalFormationContext,
        previous_plan: Optional[Dict[str, Any]],
        fingerprint: str,
    ) -> bool:
        if not isinstance(previous_plan, dict):
            return False
        formation = previous_plan.get("goal_formation")
        if not isinstance(formation, dict):
            return False
        if str(formation.get("context_fingerprint") or "") != fingerprint:
            return False
        # Safety / hazards always re-evaluate
        if context.dominant_need == "safety" or (context.perception or {}).get("hazards"):
            return False
        disposition = str(formation.get("disposition") or "")
        if disposition in {"select", "resume", "supersede", "defer"}:
            return True
        return False

    def _trace(self, event: str, decision: GoalFormationDecision, note: str = "") -> None:
        self._trace_event(
            event,
            reason=decision.reason,
            metadata={
                "intent": decision.selected_intent,
                "disposition": decision.disposition.value,
                "features": decision.features,
                "rejected_alternatives": decision.rejected[:6],
                "reused": decision.reused,
                "note": note,
                "fingerprint": decision.context_fingerprint,
                "superseded_goal_id": decision.superseded_goal_id,
            },
            goal_id=(decision.selected_goal.id if decision.selected_goal else "formation"),
        )

    def _trace_event(
        self,
        decision: str,
        *,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        goal_id: str = "formation",
    ) -> None:
        if self.traces is None:
            return
        self.traces.record(
            goal_id=goal_id,
            decision=decision,
            reason=reason,
            next_action="plan" if decision == "goal_selected" else "idle",
            metadata=dict(metadata or {}),
        )


__all__ = [
    "GoalFormationService",
    "needs_from_snapshot",
    "normalize_need_scores",
    "context_fingerprint",
]
