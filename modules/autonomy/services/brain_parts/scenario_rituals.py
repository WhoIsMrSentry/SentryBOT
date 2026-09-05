from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.scenario_rituals")


class ScenarioRitualsMixin:
    """Proactive behaviors, companion rituals, auto-execution ticking, and scenario replays."""

    state: Dict[str, Any]
    config: Dict[str, Any]
    mood: Any
    client: Any
    memory: Any
    proactive_planner: Any
    companion_rituals: Any
    companion_lines: Any
    goal_selector: Any
    goal_auto_execute_gate: Any
    execute_companion_goal: Any

    def _record_companion_outcome(
        self, plan: dict | None, result: dict | None, *, now: float | None = None
    ) -> dict:
        """Record a bounded, selector-consumable summary of the most recent companion action."""
        cfg = self.config.get("outcome_learning", {}) if isinstance(getattr(self, "config", {}), dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        if not bool(cfg.get("enabled", False)):
            return {"ok": False, "available": False, "reason": "outcome_learning_disabled"}
        action_plan = plan if isinstance(plan, dict) else {}
        execution = result if isinstance(result, dict) else {}
        timestamp = float(now if now is not None else time.time())
        lifecycle = execution.get("lifecycle", {}) if isinstance(execution.get("lifecycle"), dict) else {}
        state = str(lifecycle.get("state") or "")
        succeeded = bool(execution.get("ok")) and state not in {"blocked", "failed", "cancelled"}
        delta = float(
            cfg.get("success_weight_adjustment", 0.0) if succeeded else cfg.get("failure_weight_adjustment", 0.0)
        )
        dominant = str(action_plan.get("dominant_need") or "").strip()
        adjustments = {dominant: delta} if dominant else {}
        outcome = {
            "timestamp": timestamp,
            "plan_id": action_plan.get("plan_id"),
            "behavior": action_plan.get("behavior"),
            "succeeded": succeeded,
            "lifecycle_state": state,
            "reason": execution.get("reason"),
            "candidate_weight_adjustments": adjustments,
            "temporary_avoid_tags": list(cfg.get("failure_avoid_tags", [])) if not succeeded else [],
        }
        self.state["companion_outcome"] = outcome
        return {"ok": True, "available": True, "outcome": outcome}

    def run_companion_e2e_scenario(self, payload: Optional[dict] = None) -> dict:
        """Replay ordered companion decision inputs without commanding hardware."""
        data = payload if isinstance(payload, dict) else {}
        timeline = data.get("timeline") or data.get("steps") or []
        timeline = timeline if isinstance(timeline, list) else []
        results = []
        all_passed = True
        for index, raw_step in enumerate(timeline):
            step = raw_step if isinstance(raw_step, dict) else {}
            snapshot = dict(step.get("needs_snapshot") or step.get("needs") or {})
            for field in (
                "perception",
                "audio",
                "memory",
                "capability_health",
                "outcome_learning",
                "reflection_policy",
            ):
                value = step.get(field)
                if isinstance(value, dict):
                    snapshot[field] = dict(value)
            owner_present = bool(step.get("owner_present", False))
            timestamp = float(step.get("timestamp", index))
            plan = self.goal_selector.select(snapshot, owner_present=owner_present, now=timestamp)
            expected = step.get("expected") if isinstance(step.get("expected"), dict) else {}
            checks = {}
            expected_map = {
                "recommended_goal": plan.get("recommended_goal"),
                "behavior": plan.get("behavior"),
                "semantic": plan.get("pet_expression_hint"),
                "suppressed": bool(plan.get("suppressed") or not plan.get("auto_execute", True)),
            }
            for field, actual in expected_map.items():
                if field in expected:
                    checks[field] = {"expected": expected[field], "actual": actual, "passed": expected[field] == actual}
            explanation_fragment = str(expected.get("explanation_contains") or "")
            if explanation_fragment:
                explanation = str(plan.get("decision_explanation") or "")
                checks["explanation_contains"] = {
                    "expected": explanation_fragment,
                    "actual": explanation,
                    "passed": explanation_fragment in explanation,
                }
            passed = all(item.get("passed", False) for item in checks.values()) if checks else True
            all_passed = all_passed and passed
            results.append({
                "index": index,
                "timestamp": timestamp,
                "plan": plan,
                "checks": checks,
                "passed": passed,
            })
        outcome = {
            "ok": all_passed,
            "available": True,
            "replay": True,
            "step_count": len(results),
            "passed_count": sum(1 for item in results if item["passed"]),
            "steps": results,
        }
        self.state["companion_e2e_scenario"] = outcome
        return outcome

    def get_companion_auto_execute_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_auto_execute")
            if isinstance(current, dict) and current:
                return dict(current)
            if hasattr(self, "goal_auto_execute_gate"):
                status = self.goal_auto_execute_gate.status()
                status["available"] = False
                status["reason"] = "never_checked"
                return status
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "auto_execute_gate_missing"}

    def tick_companion_auto_execute(self, payload: Optional[dict] = None, force: bool = False, **_: object) -> dict:
        try:
            body = payload if isinstance(payload, dict) else {}
            plan = body.get("goal_plan") if isinstance(body.get("goal_plan"), dict) else None
            if not isinstance(plan, dict):
                plan = self.get_companion_goal_snapshot() if hasattr(self, "get_companion_goal_snapshot") else {}
            decision = self.goal_auto_execute_gate.decide(plan, force=force)
            if not decision.get("should_execute"):
                self.state["companion_auto_execute"] = decision
                return decision
            execution = self.execute_companion_goal({"goal_plan": plan})
            result = self.goal_auto_execute_gate.mark_execution(decision, execution)
            self.state["companion_auto_execute"] = result

            if plan.get("behavior") == "llm_generated_action" and hasattr(self, "reflection_planner"):
                needs = self.get_needs_snapshot() if hasattr(self, "get_needs_snapshot") else {}
                vision = self.state.get("vision_context_needs", {}).get("summary", "no context")

                def _reflect_and_store():
                    # C4: reflection writes memory/social_db from a side
                    # thread — serialize against the brain dream-cycle's
                    # prune/consolidate pass via the shared write lock.
                    lock = getattr(self, "_memory_write_lock", None)
                    try:
                        if lock is not None:
                            with lock:
                                reflection_mem = self.reflection_planner.reflect(plan, result, needs, vision)
                                if reflection_mem and hasattr(self, "observe_world_memory"):
                                    self.observe_world_memory(reflection_mem, source="reflection_planner")
                        else:
                            reflection_mem = self.reflection_planner.reflect(plan, result, needs, vision)
                            if reflection_mem and hasattr(self, "observe_world_memory"):
                                self.observe_world_memory(reflection_mem, source="reflection_planner")
                    except Exception as e:
                        logger.error(f"Reflection failed: {e}")

                threading.Thread(target=_reflect_and_store, daemon=True).start()

                threading.Thread(target=_reflect_and_store, daemon=True).start()

            return result
        except Exception as exc:
            return {"ok": False, "available": False, "should_execute": False, "executed": False, "error": str(exc)}

    def _run_companion_rituals(self, now: float) -> None:
        if getattr(self, "_speech_busy", False):
            return
        owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
        plan = self.companion_rituals.propose(
            now_ts=now,
            owner_present=owner_present,
            is_sleeping=bool(self.state.get("is_sleeping", False)),
            line_generator=self.companion_lines,
            needs=self.mood.get_needs() if hasattr(self.mood, "get_needs") else {},
            dominant_emotion=str(self.mood.get_dominant_emotion() or "neutral"),
            absence_s=max(0.0, self._owner_absence_seconds(now)),
        )
        if not plan:
            return
        text = str(plan.get("text", "")).strip()
        if not text:
            return
        emotion = str(plan.get("emotion", "joy")).strip()
        event = str(plan.get("event", "companion.ritual")).strip()
        try:
            self.client.push_interaction_event(event, {"text": text, "emotion": emotion})
        except TypeError:
            self.client.push_interaction_event(event)
        self._speak_with_mood(text, emotion=emotion)
        self.memory.add_event(f"Companion ritual: {text}")
        logger.info("Companion ritual fired | event=%s emotion=%s text=%s", event, emotion, text)

    def _run_companion_proactive(self, now: float) -> None:
        if self.state.get("is_sleeping"):
            return
        if getattr(self, "_speech_busy", False):
            return
        idle_s = max(0.0, now - float(self.state.get("last_interaction", now)))
        dominant = str(self.mood.get_dominant_emotion() or "neutral")
        speaker = str(self.state.get("last_speaker") or "")
        owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
        social_profile = self.relationship_memory.social_profile(speaker) if speaker else {}
        scene_ctx = {
            "summary": str(self.state.get("scene_summary", "") or ""),
            "importance": float(self.state.get("scene_importance", 0.0) or 0.0),
            "unspoken": bool(self.state.get("scene_unspoken", False)),
        }
        plan = self.proactive_planner.propose(
            now_ts=now,
            idle_s=idle_s,
            dominant_emotion=dominant,
            last_speaker=speaker,
            owner_present=owner_present,
            social_profile=social_profile,
            scene=scene_ctx,
            needs=self.mood.get_needs() if hasattr(self.mood, "get_needs") else {},
        )
        if not plan:
            return
        text = str(plan.get("text", "")).strip()
        if not text:
            return
        if plan.get("scene_consumed"):
            self.state["scene_unspoken"] = False
        emotion = str(plan.get("emotion", "curiosity")).strip()
        event = str(plan.get("event", "companion.proactive")).strip()
        try:
            self.client.push_interaction_event(event, {"text": text, "emotion": emotion})
        except TypeError:
            self.client.push_interaction_event(event)
        self._speak_with_mood(text, emotion=emotion)
        self.memory.add_event(f"Proactive companion line: {text}")
        logger.info("Companion proactive fired | event=%s emotion=%s text=%s", event, emotion, text)
