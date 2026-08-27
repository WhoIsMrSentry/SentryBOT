from __future__ import annotations

import datetime
import logging
import random
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy")


class DecisionMixin:
    """Think loop, idle actions, sleep cycles and agentic decision making."""

    config: Dict[str, Any]
    state: Dict[str, Any]
    mood: Any
    memory: Any
    client: Any
    agent: Any
    relationship_memory: Any
    world_memory: Any
    _last_idle_action: float
    _last_agentic_ts: float
    _last_alone_appraisal_ts: float
    _last_darkness_appraisal_ts: float
    _agentic_decision_in_progress: bool
    _agentic_decision_lock: Any
    _worker_executor: Any

    def _think(self) -> None:
        now = time.time()
        self._ensure_timeline_day()
        self._refresh_rfid_authorization()

        if self._companion_paused() and not self.state.get("is_sleeping"):
            try:
                op = self.client.get_operational_mode()
                from ..brain import _PAUSED_OPERATIONAL
                if str(op).strip().lower() in _PAUSED_OPERATIONAL:
                    self.state["is_sleeping"] = str(op).strip().lower() == "sleep"
            except Exception:
                pass

        self._check_sleep_cycle()
        if self.state["is_sleeping"]:
            if random.random() < 0.1:
                self.client.set_neopixel("breathe", emotions=["neutral"], duration=2.0)

            last_prune = self.state.get("last_memory_prune_ts", 0)
            if now - last_prune > 3600:
                logger.info("Dream Cycle: Pruning and consolidating memories...")
                mem_lock = getattr(self, "_memory_write_lock", None)
                try:
                    if mem_lock is not None:
                        with mem_lock:
                            prune_res = self.world_memory.prune_unimportant_memories()
                            cons_res = self.world_memory.consolidate_memories()
                    else:
                        prune_res = self.world_memory.prune_unimportant_memories()
                        cons_res = self.world_memory.consolidate_memories()
                    logger.info(
                        f"Dream Cycle complete. Pruned: {prune_res.get('deleted', 0)}, "
                        f"Consolidated: {cons_res.get('consolidated', 0)}"
                    )
                except Exception as exc:
                    logger.error(f"Dream cycle failed: {exc}")

                try:
                    social_db = getattr(self, "social_db", None)
                    if social_db is not None and hasattr(social_db, "purge_old_data"):
                        p_res = social_db.purge_old_data(max_age_days=7.0)
                        logger.info("Dream Cycle: Purged SocialDB events: %s", p_res)
                except Exception as p_exc:
                    logger.debug("SocialDB purge skipped in dream cycle: %s", p_exc)

                self.state["last_memory_prune_ts"] = now

            return

        self.mood.update()
        self._sync_emotion()
        self._liveliness_tick(now)

        self._update_companion_needs(now)

        if random.random() < 0.4:
            self._perform_micro_movement()

        self._maybe_scan_for_owner()
        self._check_owner_presence_appraisal(now)
        self._forward_visual_events_to_agent()

        boredom_threshold = self.config.get("defaults", {}).get("boredom_threshold_s", 20)
        time_since_interaction = now - self.state["last_interaction"]
        if time_since_interaction > boredom_threshold:
            if not self.state["is_bored"]:
                logger.info("Robot is bored.")
                self.state["is_bored"] = True
                self.mood.modify("curiosity", 10)
                self.memory.add_event("I became bored because nothing happened for a while.")
            idle_cfg = self.config.get("behaviors", {}).get("idle_tree", {})
            idle_interval = float(idle_cfg.get("interval_s", 6.0))
            if now - self._last_idle_action >= idle_interval:
                agentic_enabled = bool(idle_cfg.get("fallback_to_llm", True)) or bool(
                    self.config.get("agentic", {}).get("enabled", True)
                )
                if agentic_enabled and self._should_agentic_decision(now):
                    if self._submit_agentic_decision("boredom"):
                        self._last_agentic_ts = now
                        self._last_idle_action = now
        else:
            self.state["is_bored"] = False

        alone_threshold = float(self.config.get("defaults", {}).get("alone_threshold_s", 120))
        if time_since_interaction > alone_threshold and (now - self._last_alone_appraisal_ts) > alone_threshold:
            if self.appraise_event("alone_too_long", emit=True):
                self._last_alone_appraisal_ts = now

        self._run_companion_rituals(now)
        self._run_companion_proactive(now)

    def _check_darkness_appraisal(self, now: float) -> None:
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled"):
            return
        hour = datetime.datetime.now().hour
        start = int(sleep_cfg.get("start_hour", 3))
        end = int(sleep_cfg.get("end_hour", 6))
        if start > end:
            dark = hour >= start or hour < end
        else:
            dark = start <= hour < end
        if not dark:
            return
        if (now - self._last_darkness_appraisal_ts) < 300:
            return
        if self.appraise_event("darkness", emit=False):
            self._last_darkness_appraisal_ts = now

    def _should_agentic_decision(self, now: float) -> bool:
        cfg = self.config.get("agentic", {}) if isinstance(self.config.get("agentic"), dict) else {}
        if not cfg.get("enabled", True):
            return False
        min_interval = float(cfg.get("min_interval_s", 45.0))
        if now - self._last_agentic_ts < min_interval:
            return False
        triggers = cfg.get("triggers", {}) if isinstance(cfg.get("triggers"), dict) else {}
        needs = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
        if float(needs.get("social", 0)) >= float(triggers.get("social_need", 72)):
            return True
        if float(needs.get("stimulation", 0)) >= float(triggers.get("stimulation_need", 68)):
            return True
        if float(self.mood.state.get("energy", 100) or 100) <= float(triggers.get("low_energy", 25)):
            return True
        if float(needs.get("rest", 100)) <= float(triggers.get("low_rest", 22)):
            return True
        return random.random() < float(cfg.get("fallback_random_chance", 0.12))

    def _mood_trend_summary(self) -> str:
        db = getattr(self.mood, "_social_db", None)
        if db is None:
            return ""
        try:
            rows = db.mood_snapshots.recent(limit=5)
            if len(rows) < 2:
                return ""
            latest = rows[0]
            oldest = rows[-1]
            dh = float(latest.get("happiness", 0)) - float(oldest.get("happiness", 0))
            de = float(latest.get("energy", 0)) - float(oldest.get("energy", 0))
            return f"mood_trend happiness {dh:+.0f}, energy {de:+.0f} over {len(rows)} snapshots"
        except Exception:
            return ""

    def _last_sighting_summary(self, speaker: str = "") -> str:
        db = getattr(self.mood, "_social_db", None)
        if db is None:
            return ""
        try:
            rows = db.sightings.recent(limit=3)
            if not rows:
                return ""
            last = rows[0]
            ago = int(max(0, time.time() - float(last.get("ts", 0))))
            return f"last sighting {ago}s ago (person_id={last.get('person_id', '?')})"
        except Exception:
            return ""


    def _try_begin_agentic_decision(self) -> bool:
        """Reserve the single agentic-decision worker slot."""
        lock = getattr(self, "_agentic_decision_lock", None)
        if lock is None:
            if getattr(self, "_agentic_decision_in_progress", False):
                return False
            self._agentic_decision_in_progress = True
            return True
        with lock:
            if getattr(self, "_agentic_decision_in_progress", False):
                return False
            self._agentic_decision_in_progress = True
            return True

    def _finish_agentic_decision(self) -> None:
        """Release the single agentic-decision worker slot."""
        lock = getattr(self, "_agentic_decision_lock", None)
        if lock is None:
            self._agentic_decision_in_progress = False
            return
        with lock:
            self._agentic_decision_in_progress = False

    def _submit_agentic_decision(self, reason: str = "boredom", context_note: str = "") -> bool:
        """Start one agentic decision if none is already running."""
        if not self._try_begin_agentic_decision():
            return False
        try:
            executor = getattr(self, "_worker_executor", None)
            if executor is not None:
                executor.submit(self._make_agentic_decision, reason, context_note)
            else:
                self._make_agentic_decision(reason=reason, context_note=context_note)
            return True
        except Exception:
            self._finish_agentic_decision()
            raise

    def _make_agentic_decision(self, reason: str = "boredom", context_note: str = "") -> None:
        try:
            if not self.config.get("llm", {}).get("enabled", False):
                return
    
            events = "\n".join(self.memory.get_recent_events())
            social_context = self.relationship_memory.build_social_context(
                current_speaker=str(self.state.get("last_speaker") or "")
            )
            pref_summary = self._preference_summary()
            habits_summary = self._habits_summary() if hasattr(self, "_habits_summary") else ""
            activity = self._recent_companion_activity_summary()
            needs = self.mood.get_needs() if hasattr(self.mood, "get_needs") else {}
            mood_trend = self._mood_trend_summary()
            sighting = self._last_sighting_summary(str(self.state.get("last_speaker") or ""))

            # Peripheral Vision Scene Summary
            scene_summary = ""
            if hasattr(self, "scene_register") and self.scene_register is not None:
                try:
                    scene_summary = self.scene_register.get_scene_summary()
                except Exception as s_exc:
                    logger.debug("Failed getting scene summary: %s", s_exc)

            situation = "You are currently IDLE with unmet needs."
            if reason == "vision":
                situation = f"You just noticed something visually: {context_note}"
            elif reason == "audio":
                situation = f"You just heard something: {context_note}"
            elif reason == "social":
                situation = f"Social context update: {context_note}"
            elif reason == "memory":
                situation = f"You just remembered something: {context_note}"

            env_text = f"Environment (Peripheral Vision):\n{scene_summary}\n\n" if scene_summary else ""
            pref_text = f"Preferences: {pref_summary}\n" if pref_summary else ""
            habits_text = f"Habits & Patterns: {habits_summary}\n" if habits_summary else ""
            act_text = f"Recent activity: {activity}\n" if activity else ""

            prompt = (
                f"{situation}\n"
                f"Internal State:\n"
                f"- Happiness: {int(self.mood.state['happiness'])}/100, Energy: {int(self.mood.state['energy'])}/100, "
                f"Curiosity: {int(self.mood.state['curiosity'])}/100\n"
                f"- Needs: social={needs.get('social', 0)}, stimulation={needs.get('stimulation', 0)}, "
                f"rest={needs.get('rest', 0)}\n"
                f"Recent Events:\n{events}\n\n"
                f"{env_text}"
                f"{social_context}\n"
                f"{pref_text}"
                f"{habits_text}"
                f"{act_text}"
                f"{mood_trend}\n{sighting}\n\n"
                f"Runtime tools will be provided separately by Agent Core. Use only those tool schemas; "
                f"never invent tool names or arguments. Prefer one safe, small action. "
                f"For embodied reactions, prefer express_emotion or speak when available. "
                f"For lighting, use set_lights only with its schema. "
                f"Do not use raw movement or laser actions. "
                f"Act first through a tool when action is needed, then keep any final text brief."
            )

            try:
                if self.agent:
                    self.agent.memory.remember("agentic_decision", "I got bored so I decided to act on my own.")
                    res = self.agent.step(prompt)
                    if isinstance(res, dict):
                        # Free-plan orchestration through BehaviorComposer
                        plan_payload = res.get("plan") if isinstance(res.get("plan"), dict) else None
                        if plan_payload is None and any(k in res for k in ("look", "posture", "vocal_sound", "wake_when")):
                            plan_payload = res

                        if plan_payload and hasattr(self, "behavior_composer") and self.behavior_composer is not None:
                            try:
                                self.behavior_composer.execute_plan(plan_payload)
                            except Exception as comp_exc:
                                logger.warning("BehaviorComposer execution failed: %s", comp_exc)

                        actions = res.get("actions") if isinstance(res.get("actions"), list) else []
                        action_tools = {
                            str(action.get("tool", "")).strip().lower()
                            for action in actions
                            if isinstance(action, dict)
                        }
                        voice_action_used = bool(res.get("speech_handled")) or bool(
                            action_tools.intersection({"speak", "express_emotion", "set_emotion"})
                        )
                        for action in actions:
                            if not isinstance(action, dict):
                                continue
                            if str(action.get("tool", "")).strip().lower() != "queue_action":
                                continue
                            args = action.get("args") if isinstance(action.get("args"), dict) else {}
                            if str(args.get("action_type", "")).strip().lower() == "speak":
                                voice_action_used = True
                                break

                        final_text = str(res.get("text") or "").strip()
                        if final_text and not voice_action_used and not (plan_payload and plan_payload.get("say")):
                            self._speak_with_mood(final_text)
                        if final_text or actions or plan_payload:
                            self.appraise_event("command_ok", emit=False)
                else:
                    logger.warning("Agent Core is disabled. Cannot make native decision.")
            except Exception as exc:
                logger.error("Agentic decision failed natively: %s", exc)
                self.appraise_event("command_failed", emit=False)
        finally:
            self._finish_agentic_decision()
    def _check_sleep_cycle(self) -> None:
        sleep_cfg = self.config.get("behaviors", {}).get("sleep", {})
        if not sleep_cfg.get("enabled", False):
            return

        hour = datetime.datetime.now().hour
        start = sleep_cfg.get("start_hour", 3)
        end = sleep_cfg.get("end_hour", 6)

        if start > end:
            should_sleep = hour >= start or hour < end
        else:
            should_sleep = start <= hour < end

        if should_sleep and not self.state["is_sleeping"]:
            logger.info("Going to sleep...")
            self._check_darkness_appraisal(time.time())
            self._deliver_timeline_summary()
            self.state["is_sleeping"] = True
            self.memory.add_event("Going to sleep now.")
            self.client.push_interaction_event("autonomy.sleep")
            ran = self._run_scene("sleepy_entry", context={"hour": hour})
            if not ran:
                self.client.queue_action("head_move", priority=70, payload={"pan": 90, "tilt": 120})
                self._speak_with_mood("İyi geceler.", emotion="tired")
            self.client.set_speech_tracking(False)

        elif not should_sleep and self.state["is_sleeping"]:
            logger.info("Waking up!")
            self.state["is_sleeping"] = False
            self.memory.add_event("Waking up from sleep.")
            self.appraise_event("rested")
            if hasattr(self.mood, "satisfy_need"):
                rest_fill = float(
                    self.config.get("defaults", {})
                    .get("mood", {})
                    .get("needs", {})
                    .get("rest", {})
                    .get("sleep_fill", 35)
                )
                self.mood.satisfy_need("rest", rest_fill)
            self.mood.modify("energy", 100)
            self.client.push_interaction_event("autonomy.wake")
            if not self._run_scene("wake_entry", context={"hour": hour}):
                self._speak_with_mood("Günaydın.", emotion="joy")
            self.client.set_speech_tracking(True)
