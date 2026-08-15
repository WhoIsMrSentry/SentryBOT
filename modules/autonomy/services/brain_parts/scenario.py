from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.scenario")


class CompanionScenarioMixin:
    """Mixin for companion need updates, routines, scenario replays, and outcome learning."""

    def _update_companion_routines(self, snapshot: dict) -> dict:
        companion_cfg = self.config.get("companion_goals", {})
        companion_cfg = companion_cfg if isinstance(companion_cfg, dict) else {}
        autonomy_cfg = companion_cfg.get("autonomy_policy", {})
        autonomy_cfg = autonomy_cfg if isinstance(autonomy_cfg, dict) else {}
        policy = autonomy_cfg.get("routine_learning", {})
        policy = policy if isinstance(policy, dict) else {}
        routines = self.state.get("companion_routines", {})
        routines = dict(routines) if isinstance(routines, dict) else {}
        if not bool(policy.get("enabled", False)):
            return routines
        perception = snapshot.get("perception", {})
        if (
            bool(policy.get("requires_owner_present", False))
            and not bool(perception.get("owner_present", False))
            if isinstance(perception, dict)
            else bool(policy.get("requires_owner_present", False))
        ):
            return routines
        observations = self.state.get("companion_routine_observations", {})
        observations = dict(observations) if isinstance(observations, dict) else {}
        minimum = max(1, int(policy.get("min_observations", 1) or 1))
        for routine_name, paths in (policy.get("signals", {}) or {}).items():
            values = []
            for path in paths if isinstance(paths, list) else [paths]:
                current: object = snapshot
                for part in str(path).split("."):
                    current = current.get(part) if isinstance(current, dict) else None
                if current is not None:
                    values.append(bool(current))
            active = bool(values) and any(values)
            count = int(observations.get(str(routine_name), 0) or 0)
            observations[str(routine_name)] = count + 1 if active else 0
            routines[str(routine_name)] = observations[str(routine_name)] >= minimum
        self.state["companion_routine_observations"] = observations
        self.state["companion_routines"] = routines
        return routines

    def _update_companion_needs(self, now: float) -> None:
        try:
            owner_present = bool(self._owner_seen_recently()) if hasattr(self, "_owner_seen_recently") else False
            owner_last_seen = float(self.state.get("owner_last_seen", 0.0) or 0.0)
            scene_ctx = {
                "summary": str(self.state.get("scene_summary", "") or ""),
                "importance": float(self.state.get("scene_importance", 0.0) or 0.0),
                "unspoken": bool(self.state.get("scene_unspoken", False)),
                "hazards": self.state.get("scene_hazards", []),
            }
            cfg_pc = self.config.get("pc_test", {}) if isinstance(self.config.get("pc_test", {}), dict) else {}
            pc_test = bool(cfg_pc.get("enabled", False))
            mood_state = getattr(self.mood, "state", {})
            mood_state = dict(mood_state) if isinstance(mood_state, dict) else {}
            needs_state = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
            needs_state = dict(needs_state) if isinstance(needs_state, dict) else {}
            if hasattr(self, "vision_context_needs_bridge"):
                try:
                    bridge_ctx = self.vision_context_needs_bridge.context(now=now)
                    self.state["vision_context_needs"] = bridge_ctx.get("status", bridge_ctx)
                    if bridge_ctx.get("available"):
                        scene_ctx.update(bridge_ctx.get("scene") or {})
                        if bridge_ctx.get("owner_present"):
                            owner_present = True
                        bridge_owner_ts = bridge_ctx.get("owner_last_seen_ts")
                        if bridge_owner_ts:
                            owner_last_seen = max(float(owner_last_seen or 0.0), float(bridge_owner_ts))
                        mood_state.update(bridge_ctx.get("mood_overrides") or {})
                        needs_state.update(bridge_ctx.get("needs_overrides") or {})
                except Exception as exc:
                    logger.debug("Vision context needs bridge failed: %s", exc)
            if hasattr(self, "audio_event_needs_bridge"):
                try:
                    audio_bridge_ctx = self.audio_event_needs_bridge.context(now=now)
                    self.state["audio_event_needs"] = audio_bridge_ctx.get("status", audio_bridge_ctx)
                    if audio_bridge_ctx.get("available"):
                        scene_ctx["audio_context"] = audio_bridge_ctx.get("audio_context") or {}
                        if audio_bridge_ctx.get("owner_present"):
                            owner_present = True
                        audio_owner_ts = audio_bridge_ctx.get("owner_last_heard_ts")
                        if audio_owner_ts:
                            owner_last_seen = max(float(owner_last_seen or 0.0), float(audio_owner_ts))
                        if audio_bridge_ctx.get("speech_busy"):
                            setattr(self, "_speech_busy", True)
                        mood_state.update(audio_bridge_ctx.get("mood_overrides") or {})
                        needs_state.update(audio_bridge_ctx.get("needs_overrides") or {})
                except Exception as exc:
                    logger.debug("Audio event needs bridge failed: %s", exc)
            snapshot = self.needs_engine.tick(
                now=now,
                last_interaction_ts=float(self.state.get("last_interaction", now) or now),
                mood_state=mood_state,
                needs_state=needs_state,
                owner_present=owner_present,
                owner_last_seen_ts=owner_last_seen or None,
                is_sleeping=bool(self.state.get("is_sleeping", False)),
                speech_busy=bool(getattr(self, "_speech_busy", False)),
                scene=scene_ctx,
                pc_test=pc_test,
            )
            snapshot = self._apply_memory_bias_to_needs(snapshot, now)
            try:
                people = self.relationship_memory.top_people(limit=5)
                owner_record = next(
                    (person for person in people if isinstance(person, dict) and bool(person.get("is_owner", False))),
                    None,
                )
                if owner_record is None and people:
                    owner_record = people[0] if isinstance(people[0], dict) else None
                preferences = (
                    dict(owner_record.get("preferences", {}))
                    if isinstance(owner_record, dict) and isinstance(owner_record.get("preferences", {}), dict)
                    else {}
                )
                snapshot["preferences"] = preferences
                snapshot["relationship"] = {"preferences": preferences}
            except Exception:
                snapshot.setdefault("preferences", {})
                snapshot.setdefault("relationship", {"preferences": {}})
            snapshot["routines"] = self._update_companion_routines(snapshot)

            snapshot["perception"] = self.get_canonical_perception_context(snapshot.get("perception", {}))
            snapshot["capability_health"] = self.get_capability_health_snapshot()
            self.state["companion_needs"] = snapshot
            social_people = (
                snapshot.get("perception", {}).get("people", [])
                if isinstance(snapshot.get("perception"), dict)
                else []
            )
            social_cfg = self.config.get("social_policy", {}) if isinstance(self.config, dict) else {}
            social_cfg = social_cfg if isinstance(social_cfg, dict) else {}
            if hasattr(self, "relationship_memory") and isinstance(social_people, list):
                for person in social_people:
                    if not isinstance(person, dict):
                        continue
                    name = str(person.get("name") or person.get("label") or "").strip()
                    if name:
                        try:
                            person["person_type"] = self.relationship_memory.classify_person(
                                name,
                                known_guest_min_seen_count=int(social_cfg.get("known_guest_min_seen_count", 0) or 0),
                            )
                        except Exception:
                            person.setdefault("person_type", "unknown_guest")
            previous_outcome = self.state.get("companion_outcome")
            if isinstance(previous_outcome, dict):
                snapshot["outcome_learning"] = dict(previous_outcome)
            goal_plan = self.goal_selector.select(
                snapshot,
                owner_present=owner_present,
                now=now,
            )
            self.state["companion_goal"] = goal_plan
            goal_event = str(goal_plan.get("event", "") or "").strip()
            if goal_event:
                try:
                    self.client.push_interaction_event(goal_event, goal_plan)
                except TypeError:
                    self.client.push_interaction_event(goal_event)
            event = str(snapshot.get("event", "") or "").strip()
            if event:
                payload = {
                    "dominant_need": snapshot.get("dominant_need"),
                    "recommended_goal": snapshot.get("recommended_goal"),
                    "scores": snapshot.get("scores", {}),
                    "confidence": snapshot.get("confidence", 0.0),
                }
                try:
                    self.client.push_interaction_event(event, payload)
                except TypeError:
                    self.client.push_interaction_event(event)
        except Exception as exc:
            logger.debug("Companion needs update failed: %s", exc)

    def execute_companion_goal(self, payload: Optional[dict] = None, **_: object) -> dict:
        try:
            plan = None
            if isinstance(payload, dict) and isinstance(payload.get("goal_plan"), dict):
                plan = payload.get("goal_plan")
            if not isinstance(plan, dict):
                plan = self.get_companion_goal_snapshot() if hasattr(self, "get_companion_goal_snapshot") else {}

            if plan and "actions" in plan:
                native_actions = [a for a in plan.get("actions", []) if a.get("native_tool_call")]
                for action in native_actions:
                    if getattr(self, "agent", None) and hasattr(self.agent, "tool_registry"):
                        tool_name = action.get("tool")
                        kwargs = {k: v for k, v in action.items() if k not in ["tool", "native_tool_call"]}
                        try:
                            logger.info(f"Executing native tool call from plan: {tool_name}({kwargs})")
                            self.agent.tool_registry.execute(tool_name, kwargs)
                        except Exception as e:
                            logger.error(f"Failed to execute native tool {tool_name}: {e}")

            if hasattr(self, "goal_executor"):
                result = self.goal_executor.execute(plan)
                self.state["companion_goal_execution"] = result
                self._record_companion_outcome(plan, result)
                return result
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["companion_goal_execution"] = result
            return result
        return {"ok": False, "available": False, "reason": "goal_executor_missing"}

    def _apply_memory_bias_to_needs(self, snapshot: dict, now: float | None = None) -> dict:
        try:
            if (
                not hasattr(self, "memory_needs_bias")
                or not hasattr(self, "memory_decision_shadow")
                or not hasattr(self, "world_memory")
            ):
                return snapshot
            memory_snapshot = self.world_memory.status()
            recent_result = self.world_memory.recent(limit=25)
            recent = recent_result.get("items", []) if isinstance(recent_result, dict) else []
            shadow = self.memory_decision_shadow.evaluate(memory_snapshot, recent, now=now)
            self.state["memory_decision_shadow"] = shadow
            biased = self.memory_needs_bias.apply(snapshot, shadow, now=now)
            if isinstance(biased, dict):
                self.state["memory_needs_bias"] = biased.get("memory_bias", {})
                return biased
        except Exception as exc:
            try:
                self.state["memory_needs_bias"] = {"ok": False, "available": False, "error": str(exc)}
            except Exception:
                pass
        return snapshot

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
                    try:
                        reflection_mem = self.reflection_planner.reflect(plan, result, needs, vision)
                        if reflection_mem and hasattr(self, "observe_world_memory"):
                            self.observe_world_memory(reflection_mem, source="reflection_planner")
                    except Exception as e:
                        logger.error(f"Reflection failed: {e}")

                threading.Thread(target=_reflect_and_store, daemon=True).start()

            return result
        except Exception as exc:
            return {"ok": False, "available": False, "should_execute": False, "executed": False, "error": str(exc)}

    def get_companion_goal_execution_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_goal_execution")
            if isinstance(current, dict) and current:
                return dict(current)
            if hasattr(self, "goal_executor"):
                status = self.goal_executor.status()
                status["available"] = False
                status["reason"] = "never_executed"
                return status
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "goal_executor_missing"}

    def get_companion_goal_snapshot(self) -> dict:
        try:
            current = self.state.get("companion_goal")
            if isinstance(current, dict) and current:
                data = dict(current)
                data["available"] = True
                return data
            needs = self.get_needs_snapshot() if hasattr(self, "get_needs_snapshot") else {}
            plan = self.goal_selector.select(needs)
            plan["available"] = False
            plan["reason"] = "no_goal_snapshot_yet"
            return plan
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_needs_snapshot(self) -> dict:
        try:
            recent_reflections = []
            if hasattr(self, "world_memory"):
                try:
                    recent = self.world_memory.recent(kind="reflection", limit=5)
                    recent_reflections = recent.get("items", [])
                except Exception:
                    pass

            tool_schemas = []
            if getattr(self, "agent", None) and hasattr(self.agent, "tool_registry"):
                tool_schemas = self.agent.tool_registry.schemas

            if hasattr(self, "living_needs") and bool(getattr(self.living_needs, "cfg", {}).get("enabled", True)):
                current = self.state.get("living_needs")
                if isinstance(current, dict) and current:
                    data = dict(current)
                    data["available"] = True
                    data["recent_reflections"] = recent_reflections
                    data["tool_schemas"] = tool_schemas
                    return data
                data = self.tick_living_needs()
                data["recent_reflections"] = recent_reflections
                data["tool_schemas"] = tool_schemas
                return data
            if hasattr(self, "needs_engine"):
                current = self.state.get("companion_needs")
                if isinstance(current, dict) and current:
                    data = dict(current)
                    data["available"] = True
                    data["recent_reflections"] = recent_reflections
                    data["tool_schemas"] = tool_schemas
                    return data
                data = self.needs_engine.snapshot()
                data["recent_reflections"] = recent_reflections
                data["tool_schemas"] = tool_schemas
                return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "needs_engine_missing"}

    def tick_living_needs(self) -> dict:
        try:
            if not hasattr(self, "living_needs"):
                return {"ok": False, "available": False, "reason": "living_needs_missing"}
            now = time.time()
            vision = self._current_vision_snapshot() if hasattr(self, "_current_vision_snapshot") else {}
            audio = self.state.get("audio_event_needs") if isinstance(self.state.get("audio_event_needs"), dict) else {}
            snapshot = self.living_needs.tick(now=now, state=self.state, mood=self.mood, vision=vision, audio=audio)
            snapshot = self._apply_memory_bias_to_needs(snapshot, now=now)
            self.state["living_needs"] = snapshot
            self.state["companion_needs"] = snapshot
            history = list(self.state.get("living_needs_history") or [])
            history.append({
                "timestamp": snapshot.get("timestamp"),
                "dominant_need": snapshot.get("dominant_need"),
                "recommended_goal": snapshot.get("recommended_goal"),
                "scores": snapshot.get("scores", {}),
            })
            self.state["living_needs_history"] = history[-50:]
            try:
                semantic = snapshot.get("semantic_state") if isinstance(snapshot.get("semantic_state"), dict) else {}
                self.client.set_expression_event(
                    "needs." + str(snapshot.get("dominant_need") or "balance"),
                    {
                        "semantic_state": semantic,
                        "scores": snapshot.get("scores", {}),
                        "recommended_goal": snapshot.get("recommended_goal"),
                    },
                )
            except Exception:
                pass
            return snapshot
        except Exception as exc:
            result = {"ok": False, "available": False, "error": str(exc)}
            self.state["living_needs"] = result
            return result

    def get_living_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("living_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "living_needs"):
                data = self.living_needs.status()
            else:
                data = {"ok": False, "available": False, "reason": "living_needs_missing"}
            data["history"] = list(self.state.get("living_needs_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

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
