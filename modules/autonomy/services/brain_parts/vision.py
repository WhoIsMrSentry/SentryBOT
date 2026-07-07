"""Vision sensing and reactions for AutonomyBrain."""
from __future__ import annotations

import random
import time
from typing import Any, Dict


class VisionMixin:
    """Handles periodic vision polling and reactions."""

    def _sense_vision(self) -> None:
        if not self._vision_cfg.get("enabled", False):
            return
        now = time.time()
        interval = self._vision_cfg.get("poll_interval_s", 3)
        last_poll = self.state.get("last_vision_poll", 0.0)
        if now - last_poll < interval:
            return
        self.state["last_vision_poll"] = now

        # Use visual context importance score to influence persona polish
        try:
            ctx_resp = self.client.get_visual_context()
            if ctx_resp and ctx_resp.get("available"):
                ctx_data = ctx_resp.get("context", {})
                importance = float(ctx_data.get("importance_score", 0.0))
                self.state["last_visual_importance"] = importance
                self._track_scene_context(ctx_data, importance)
                for person in ctx_data.get("people", []) or []:
                    if isinstance(person, dict) and person.get("emotion"):
                        self._mirror_person_emotion(
                            {
                                "name": person.get("name", "Unknown"),
                                "emotion": person.get("emotion"),
                            }
                        )
                if importance > 0.6:
                    self.mood.modify("curiosity", int(importance * 20))
                    self.mood.modify("energy", 10)
                    if self.state.get("is_bored"):
                        self.state["is_bored"] = False
                        self.memory.add_event("Saw something important, no longer bored.")
                elif importance < 0.2 and self.state.get("is_bored"):
                    self.mood.modify("happiness", -2)
        except Exception as exc:
            import logging
            logging.getLogger("autonomy.vision").debug("Failed to get visual context: %s", exc)

        max_results = self._vision_cfg.get("max_results", 5)
        results = self.client.get_latest_vision_results(limit=max_results)
        if not results:
            return
        ignored = {label.lower() for label in self._vision_cfg.get("ignore_labels", [])}
        for res in results:
            label = (res.get("label") or "").lower()
            if label in ignored:
                continue
            self._handle_vision_result(res)
        decay_window = max(10, self.owner_cfg.get("speaker_window_s", 10))
        self._current_people = {
            name: ts for name, ts in self._current_people.items() if now - ts <= decay_window
        }

    @staticmethod
    def _scene_tokens(summary: str) -> set:
        return {t for t in str(summary or "").lower().split() if len(t) > 2}

    def _track_scene_context(self, ctx_data: Dict[str, Any], importance: float) -> None:
        """Detect meaningful scene changes and remember the current surroundings.

        Keeps a short-lived snapshot of the environment in ``self.state`` so the
        proactive layer can comment on what's around, and emits an
        ``environment.scene_changed`` interaction event on novelty so other
        modules (ears/LED/agent) can react.
        """
        summary = str(ctx_data.get("summary", "") or "").strip()
        if not summary:
            return
        prev = str(self.state.get("last_scene_summary", "") or "")
        prev_tokens = self._scene_tokens(prev)
        cur_tokens = self._scene_tokens(summary)
        novelty = 1.0
        if prev_tokens:
            union = prev_tokens | cur_tokens
            novelty = (len(prev_tokens ^ cur_tokens) / len(union)) if union else 0.0

        self.state["scene_summary"] = summary
        self.state["scene_importance"] = importance

        threshold = float(self._vision_cfg.get("scene_novelty_threshold", 0.5))
        if novelty >= threshold and summary != prev:
            self.state["last_scene_summary"] = summary
            self.state["scene_changed_at"] = time.time()
            self.state["scene_unspoken"] = True  # proactive layer may narrate it
            try:
                self.client.push_interaction_event(
                    "environment.scene_changed",
                    {"summary": summary[:160], "importance": round(importance, 2)},
                )
            except Exception:
                pass
            if hasattr(self, "appraise_event"):
                self.appraise_event("scene_change", intensity=min(1.0, novelty))
            if importance >= 0.5:
                self.mood.modify("curiosity", 6)

    def _mirror_person_emotion(self, result: Dict[str, Any]) -> None:
        empathy = self._vision_cfg.get("empathy", {}) if isinstance(self._vision_cfg.get("empathy"), dict) else {}
        if not empathy.get("enabled", True):
            return
        raw = str(result.get("emotion", "") or "").strip().lower()
        if not raw:
            return
        try:
            from modules.common.emotion_vocab import get_vocab

            canon = get_vocab().canonical(raw)
        except Exception:
            canon = raw
        allowed = {str(x).strip().lower() for x in (empathy.get("mirror") or ["joy", "sadness", "fear"])}
        if canon not in allowed:
            return
        now = time.time()
        cooldown = float(empathy.get("cooldown_s", 28))
        if now - float(self.state.get("last_empathy_mirror_ts", 0.0)) < cooldown:
            return
        self.state["last_empathy_mirror_ts"] = now
        self.state["last_emotion"] = canon
        try:
            self.express(canon)
            self.client.push_interaction_event(f"vision.person_emotion_{canon}")
        except Exception:
            pass
        if empathy.get("speak_on_mirror", False):
            replies = {
                "joy": "Mutlu görünüyorsun, ben de mutlu oldum.",
                "sadness": "Üzgün görünüyorsun. İyi misin?",
                "fear": "Bir şey mi korkuttu seni?",
                "worried": "Endişeli görünüyorsun.",
            }
            line = replies.get(canon)
            if line:
                self._speak_with_mood(line, emotion=canon)

    def _handle_vision_result(self, result: Dict[str, Any]) -> None:
        name = result.get("name") or result.get("label")
        if not name:
            return
        
        import logging
        logging.getLogger("autonomy.vision").info("Vision >>> %s tespit edildi.", name)

        now = time.time()
        self._current_people[name] = now
        cooldown = self._compute_person_cooldown(result)
        last_seen = self._people_last_seen.get(name, 0.0)
        if now - last_seen < cooldown:
            return
        self._people_last_seen[name] = now
        self.state["last_interaction"] = now
        self.memory.add_event(f"Vision {name} tespit etti.")
        if name != "Unknown":
            self._track_person_stat(name)
            if hasattr(self, "_note_person_seen"):
                try:
                    self._note_person_seen(name, emotion=str(result.get("emotion", "") or ""))
                except Exception:
                    pass
        happiness_boost = 10 if name != "Unknown" else 4
        self.mood.modify("happiness", happiness_boost)
        self.mood.modify("curiosity", 5)
        self._mirror_person_emotion(result)
        self.client.push_interaction_event("vision.person", {"name": name})
        self._focus_on_target(result)
        should_speak = name != "Unknown" or self._vision_cfg.get("speak_on_unknown", False)
        if not self._should_announce_vision():
            should_speak = False
        if should_speak:
            utterance = self._compose_greeting_for_person(name, result)
            if utterance:
                emotion = "joy" if name != "Unknown" else "curiosity"
                scene_name = self._pick_vision_scene(name, result)
                ran = self._run_scene(
                    scene_name,
                    context={"name": name, "greeting": utterance, "emotion": emotion},
                )
                if not ran:
                    self._speak_with_mood(utterance, emotion=emotion)
                if hasattr(self, "appraise_event"):
                    self.appraise_event("greeted")
                self.memory.add_event(f"{name} ile konuştum: {utterance}")
        if self._is_owner_name(name):
            self._on_owner_seen(now)

    def _compose_greeting_for_person(self, name: str, result: Dict[str, Any]) -> str | None:
        if self._is_owner_name(name):
            return None
        summary = None
        try:
            record = self.client.get_person_memory(name)
            if record:
                summary = ((record.get("record") or {}).get("last_summary") or {}).get("text")
        except Exception:  # pragma: no cover - best effort enrichment
            summary = None
        distance = result.get("distance_m")
        prefer_llm = self._vision_cfg.get("prefer_llm_greetings", False)
        if prefer_llm and self.config.get("llm", {}).get("enabled", False):
            prompt = (
                "Kisa ve sicak bir selamlama uret.\n"
                f"İsim: {name}\n"
                f"Mesafe: {distance if distance else 'bilinmiyor'}\n"
                f"Özet: {summary or 'özel bilgi yok'}\n"
                f"Mutluluk: {int(self.mood['happiness'])}/100, Enerji: {int(self.mood['energy'])}/100.\n"
                "10 kelimeyi geçme, Türkçe konuş."
            )
            try:
                resp = self.client.chat(prompt)
                if resp and resp.get("answer"):
                    return resp["answer"].strip()
            except Exception:
                pass
        pieces = [f"Merhaba {name}"]
        conf = result.get("confidence")
        if isinstance(conf, (int, float)) and float(conf) < 0.5 and name != "Unknown":
            pieces = [f"Merhaba, bu kişi {name} olabilir"]
        if distance:
            try:
                pieces.append(f"yaklaşık {float(distance):.1f} metre uzaklıktasın.")
            except Exception:
                pass
        if summary:
            pieces.append(summary[:120])
        return " ".join(pieces)

    def _should_announce_vision(self) -> bool:
        threshold = float(self._vision_cfg.get("importance_speak_threshold", 0.6))
        current = float(self.state.get("last_visual_importance", 0.0) or 0.0)
        return current >= threshold

    def _focus_on_target(self, result: Dict[str, Any]) -> None:
        if self._trigger_animation("vision_focus"):
            return
        self.client.push_interaction_event("vision.focus", {"label": result.get("label")})
        cfg = self._vision_cfg.get("focus", {}) if isinstance(self._vision_cfg.get("focus", {}), dict) else {}
        min_j = int(cfg.get("jitter_min", -3))
        max_j = int(cfg.get("jitter_max", 3))
        deadband = int(cfg.get("deadband_deg", 2))
        smooth = float(cfg.get("smoothing", 0.55))

        current = int(self.state.get("current_pan", 90))
        jitter = random.randint(min_j, max_j)
        proposed = max(0, min(180, current + jitter))
        if abs(proposed - current) < max(0, deadband):
            return

        target = int(round((current * smooth) + (proposed * (1.0 - smooth))))
        self.state["current_pan"] = target
        self.client.queue_action("head_move", priority=60, payload={"pan": target, "tilt": self.state["current_tilt"]})
        self._blink_fallback()

    def _compute_person_cooldown(self, result: Dict[str, Any]) -> float:
        base = float(self._vision_cfg.get("person_cooldown_s", 25))
        dyn = self._vision_cfg.get("dynamic_cooldown", {}) if isinstance(self._vision_cfg.get("dynamic_cooldown", {}), dict) else {}
        if not bool(dyn.get("enabled", False)):
            return base
        near_dist = float(dyn.get("near_distance_m", 1.2))
        far_dist = float(dyn.get("far_distance_m", 3.0))
        near_mul = float(dyn.get("near_multiplier", 0.6))
        far_mul = float(dyn.get("far_multiplier", 1.3))
        dist = result.get("distance_m")
        if not isinstance(dist, (int, float)):
            return base
        if dist <= near_dist:
            return max(2.0, base * near_mul)
        if dist >= far_dist:
            return max(2.0, base * far_mul)
        return base

    def _pick_vision_scene(self, name: str, result: Dict[str, Any]) -> str:
        if self._is_owner_name(name):
            return "vision_greeting_owner"
        dist = result.get("distance_m")
        if name == "Unknown":
            if isinstance(dist, (int, float)) and dist <= 1.2:
                return "vision_greeting_unknown_close"
            return "vision_greeting_unknown"
        if isinstance(dist, (int, float)) and dist <= 1.2:
            return "vision_greeting_known_close"
        return "vision_greeting_known"
