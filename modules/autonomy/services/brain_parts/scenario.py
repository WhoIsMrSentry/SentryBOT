from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .scenario_rituals import ScenarioRitualsMixin

logger = logging.getLogger("autonomy.scenario")


class CompanionScenarioMixin(ScenarioRitualsMixin):
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
                                rules=social_cfg.get("person_rules"),
                            )
                        except Exception:
                            pass
            try:
                plan = self.goal_selector.select(snapshot, owner_present=owner_present, now=now)
                self.state["companion_goal"] = plan
                self._sync_companion_plan_event(plan)
            except Exception as exc:
                logger.debug("Companion goal selection failed: %s", exc)
        except Exception as exc:
            logger.debug("Companion needs update failed: %s", exc)

    def _sync_companion_plan_event(self, plan: dict) -> None:
        if not isinstance(plan, dict):
            return
        event = plan.get("event")
        if event:
            payload = {
                "dominant_need": plan.get("dominant_need"),
                "recommended_goal": plan.get("recommended_goal"),
                "behavior": plan.get("behavior"),
                "pet_intent": plan.get("pet_intent"),
                "pet_expression_hint": plan.get("pet_expression_hint"),
                "pet_motion_hint": plan.get("pet_motion_hint"),
                "pet_speech_hint": plan.get("pet_speech_hint"),
                "pet_goal_hints": plan.get("pet_goal_hints", []),
                "pet_needs_bias": plan.get("pet_needs_bias", {}),
                "pet_memory_tags": plan.get("pet_memory_tags", []),
                "priority": plan.get("priority"),
                "confidence": plan.get("confidence"),
                "scores": plan.get("scores"),
                "owner_present": plan.get("owner_present"),
                "expression_event": plan.get("expression_event"),
                "actions": plan.get("actions", []),
                "environmental_choice": plan.get("environmental_choice"),
                "autonomy_guard": plan.get("autonomy_guard"),
                "personalization": plan.get("personalization"),
                "privacy": plan.get("privacy"),
                "capability_guard": plan.get("capability_guard"),
                "outcome_learning": plan.get("outcome_learning"),
                "social_guard": plan.get("social_guard"),
                "decision_explanation": plan.get("decision_explanation"),
            }
            try:
                self.client.push_interaction_event(str(event), payload)
            except TypeError:
                self.client.push_interaction_event(str(event))

    def execute_companion_goal(self, payload: Optional[dict] = None) -> dict:
        try:
            body = payload if isinstance(payload, dict) else {}
            plan = body.get("goal_plan") if isinstance(body.get("goal_plan"), dict) else None
            if not isinstance(plan, dict):
                plan = self.get_companion_goal_snapshot()

            actions = plan.get("actions", [])
            for act in actions:
                if isinstance(act, dict) and "tool" in act:
                    tool_name = act.get("tool")
                    kwargs = {k: v for k, v in act.items() if k != "tool"}
                    if getattr(self, "agent", None) and hasattr(self.agent, "tool_registry"):
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
