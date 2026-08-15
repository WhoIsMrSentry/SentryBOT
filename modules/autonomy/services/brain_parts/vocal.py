"""Speech and tone helpers for AutonomyBrain."""
from __future__ import annotations

import datetime
import logging
import random
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    from modules.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None

logger = logging.getLogger("autonomy.vocal")


class VocalMixin:
    """Adds speaking helpers, social context recall, and speech reaction handling."""

    def _generate_monologue(self) -> None:
        if not self.config.get("llm", {}).get("enabled", False):
            return
        if time.time() < float(getattr(self, "_llm_rate_limit_until", 0.0)):
            logger.debug("Monologue skipped (LLM rate limit cooldown active)")
            return

        template = self.config.get("llm", {}).get("prompt_template", "")
        now = time.time()
        happiness = int(self.mood["happiness"])
        energy = int(self.mood["energy"])
        is_bored = "Evet" if self.state["is_bored"] else "Hayır"
        last_interaction_ago = int(now - self.state["last_interaction"])
        current_time = datetime.datetime.now().strftime("%H:%M")

        try:
            prompt = template.format(
                happiness=happiness,
                energy=energy,
                is_bored=is_bored,
                last_interaction_ago=last_interaction_ago,
                time=current_time,
            )

            resp = self.client.chat(prompt)
            if resp and "answer" in resp:
                text = resp["answer"].strip('"')
                logger.info("Monologue: %s", text)
                self._speak_with_mood(text, emotion="neutral")
                self.memory.add_event(f"Said to myself: {text}")
        except Exception as exc:
            from modules.config_center.log_redact import redact_secrets

            msg = redact_secrets(exc)
            if "429" in msg:
                self._llm_rate_limit_until = time.time() + 90.0
                logger.warning("Monologue skipped for 90s (Gemini rate limit)")
                return
            logger.error("Monologue failed: %s", msg)

    def _speak_with_mood(self, text: str, emotion: str | None = None, language: str | None = None) -> None:
        if not text:
            return
        if not language and detect_text_language:
            language = detect_text_language(text, default="tr")
        tone = self._tone_profile(emotion)
        try:
            self.client.queue_action("speak", priority=50, ttl_ms=10000, payload={
                "text": text,
                "tone": tone,
                "language": language
            })
        except Exception as exc:  # pragma: no cover - best effort speech
            logger.debug("Failed to queue speech action: %s", exc)

    _EMOTION_TONES = {
        "joy": {"rate": 190, "volume": 1.0},
        "love": {"rate": 185, "volume": 0.95},
        "excitement": {"rate": 205, "volume": 1.0},
        "surprise": {"rate": 200, "volume": 1.0},
        "curiosity": {"rate": 185, "volume": 0.9},
        "sadness": {"rate": 150, "volume": 0.75},
        "worried": {"rate": 165, "volume": 0.8},
        "tired": {"rate": 140, "volume": 0.65},
        "bored": {"rate": 150, "volume": 0.7},
        "fear": {"rate": 200, "volume": 0.9},
        "anger": {"rate": 195, "volume": 1.0},
        "furious": {"rate": 205, "volume": 1.0},
        "confusion": {"rate": 165, "volume": 0.85},
        "disgust": {"rate": 165, "volume": 0.85},
        "neutral": {"rate": 170, "volume": 0.85},
    }
    _TONE_NAME_PROFILES = {
        "joy": {"rate": 190, "volume": 1.0},
        "excited": {"rate": 200, "volume": 1.0},
        "sadness": {"rate": 150, "volume": 0.75},
        "neutral": {"rate": 170, "volume": 0.85},
    }

    def _tone_profile(self, emotion: str | None = None) -> dict:
        emotion = emotion or self.state.get("last_emotion") or self.mood.get_dominant_emotion() or "neutral"
        try:
            from modules.common.emotion_vocab import get_vocab

            vocab = get_vocab()
            canon = vocab.canonical(emotion)
            if canon in self._EMOTION_TONES:
                return dict(self._EMOTION_TONES[canon])
            tone_name = vocab.render(emotion).tone
            return dict(self._TONE_NAME_PROFILES.get(tone_name, self._TONE_NAME_PROFILES["neutral"]))
        except Exception:
            return dict(self._EMOTION_TONES.get(str(emotion).lower(), self._EMOTION_TONES["neutral"]))

    def _react_to_sound(self, angle: float) -> None:
        """Turn head towards sound source and trigger LLM reaction."""
        logger.info("Sound detected at %s", angle)
        offset = max(-70, min(70, angle))
        target_pan = max(0, min(180, 90 + offset))
        self.state["current_pan"] = target_pan
        ran = self._run_scene(
            "curious_scan",
            context={"angle": int(angle), "target_pan": int(target_pan)},
        )
        if not ran:
            self.client.queue_action(
                "head_move", priority=60, payload={"pan": target_pan, "tilt": self.state["current_tilt"]}
            )
        self.client.push_interaction_event("autonomy.excited")
        self.state["last_interaction"] = time.time()
        self.mood.modify("curiosity", 5)
        self.mood.modify("energy", 2)
        self.memory.add_event(f"Heard sound at angle {angle}")

        if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
            try:
                prompt = (
                    f"You just heard a sudden sound from angle {int(angle)} degrees. "
                    f"Your head turned toward it (pan={int(target_pan)}). "
                    f"React naturally - express curiosity, surprise, or caution. "
                    f"Use your physical tools (express_emotion, move_head, look_around, speak). "
                    f"Do not ask for permission."
                )
                self.agent.step_event("sound_detected", prompt, trace_id=f"sound_{int(time.time())}")
            except Exception as exc:
                logger.debug("Sound event step_event failed: %s", exc)

    def _barge_in_stop_speaking(self) -> None:
        """Stop robot TTS so the user can speak (wakeword barge-in)."""
        try:
            if getattr(self, "agent", None) and hasattr(self.agent, "speech_arbiter"):
                self.agent.speech_arbiter.interrupt_all()
            else:
                self.client.stop_speaking()
                self.client.interrupt_agent_speech()
        except Exception as exc:
            logger.debug("barge-in stop failed: %s", exc)

    def _robot_is_speaking(self) -> bool:
        """Best-effort check of whether TTS audio is currently playing."""
        try:
            if getattr(self, "agent", None) and hasattr(self.agent, "speech_arbiter"):
                return bool(self.agent.speech_arbiter.is_speaking())
        except Exception:
            pass
        try:
            status = self.client.get_speak_status()
            if isinstance(status, dict):
                return bool(status.get("speaking") or status.get("busy"))
        except Exception:
            pass
        return False

    def _handle_barge_in_and_wakeword(self, text: str, low: str, has_wake: bool, request_id: str) -> bool:
        from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

        if self.barge_in.should_interrupt(
            robot_speaking=self._robot_is_speaking(), user_text=text, has_wakeword=has_wake
        ):
            self._barge_in_stop_speaking()
        elif has_wake:
            self._barge_in_stop_speaking()

        if contains_wakeword(low) and len(strip_wakewords(low).split()) < 1:
            self._run_scene("wakeword_reaction", context={"text": text})
            logger.info("Wakeword-only utterance; listening for command.")
            try:
                self.client.start_speech_listening()
            except Exception:
                pass
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False
            return True
        return False

    def _handle_speech_command_shortcuts(self, text: str, lang: str, request_id: str) -> bool:
        companion_cfg = self.config.get("companion", {}) if isinstance(self.config.get("companion"), dict) else {}
        if companion_cfg.get("voice_ai_tools", True) and getattr(self, "agent", None):
            return False
        if not companion_cfg.get("emotion_command_shortcut", False):
            return False
        if self._handle_emotion_command(text, lang):
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False
            return True
        return False

    def _process_speech_social_context(self, text: str) -> str | None:
        self.mood.modify("happiness", 5)
        sentiment_event = self._sentiment_event_for_text(text)
        if sentiment_event:
            self.appraise_event(sentiment_event)
        self.memory.add_event(f"User said: {text}")
        self._log_conversation(text)
        speaker = self._guess_active_person()
        if speaker:
            self.state["last_speaker"] = speaker
            self._note_person_seen(speaker, emotion=str(self.state.get("last_emotion") or ""))
            self._remember_person_chat(speaker, text, role="user")
            if sentiment_event:
                self._apply_interaction_feedback(sentiment_event, speaker, text)
        self._maybe_emit_speech_excited(text, sentiment_event)
        return speaker

    def _handle_blocked_or_special_commands(self, text: str, speaker: str | None, lang: str) -> bool:
        blocked_response = self._maybe_block_request(text)
        if blocked_response:
            message, emotion = blocked_response
            self._speak_with_mood(message, emotion=emotion, language=lang)
            return True
        if self._handle_owner_commands(text, speaker):
            return True
        if self._features_locked_for_request(text):
            return True
        if self._handle_follow_commands(text, speaker, lang):
            return True
        return False

    def _handle_offline_mode(self, text: str, lang: str) -> bool:
        offline_cfg = self.config.get("offline_mode", {})
        if not bool(offline_cfg.get("enabled", False)):
            return False
        target_service = "ollama"
        if not self.client.is_service_available(target_service):
            fallback = self._offline_reply(text, target_service)
            self.client.push_interaction_event("autonomy.offline", {"service": target_service})
            self._speak_with_mood(fallback, emotion="neutral", language=lang)
            self.memory.add_event(f"Offline fallback reply used for {target_service}: {fallback}")
            return True
        return False

    def _try_agent_core_path(self, text: str, lang: str, speaker: str | None, request_id: str) -> bool:
        if not getattr(self, "agent", None):
            return False
        try:
            if not self.agent.speech_arbiter._speak_fn:
                self.agent.speech_arbiter.set_speak_fn(
                    lambda text, tone=None, language=None, trace_id=None: self.client.speak_preferred(
                        text,
                        tone=tone,
                        language=language or lang,
                        trace_id=trace_id,
                    )
                )
            enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
            agent_result = self.agent.step(
                enriched_text,
                language=lang,
                speaker=speaker,
                native_tools=True,
                trace_id=request_id,
            )
            if agent_result and agent_result.get("text"):
                if not self._is_active_request(request_id):
                    return True
                logger.info("Agent Core handled speech with full pipeline.")
                self.memory.add_event(f"Agent replied: {agent_result['text']}")
                self._remember_person_chat(speaker, agent_result["text"], role="assistant")
                if not agent_result.get("speech_handled"):
                    tone = self._tone_profile(self.state.get("last_emotion") or self.mood.get_dominant_emotion())
                    self.agent.speech_arbiter.enqueue_final(
                        agent_result["text"],
                        language=lang,
                        tone=tone,
                        trace_id=request_id,
                    )
                return True
        except Exception as exc:
            logger.warning("Agent Core step failed, falling back to direct LLM: %s", exc)
        return False

    def _try_direct_llm_path(self, text: str, lang: str, speaker: str | None, request_id: str) -> None:
        logger.info("Routing to Ollama...")
        enriched_text = self._enrich_user_text_with_companion_context(text=text, speaker=speaker)
        resp = self.client.chat(enriched_text, source_lang=lang, response_lang=lang)
        response_text = ""
        response_actions = None
        raw_response = None
        if resp and "answer" in resp:
            response_text = resp["answer"]
            response_actions = resp.get("actions")
            raw_response = resp.get("raw")
            trans = resp.get("translation") if isinstance(resp, dict) else None
            if isinstance(trans, dict) and trans.get("response_lang"):
                lang = str(trans.get("response_lang"))

        if not response_text:
            return
        if not self._is_active_request(request_id):
            return
        clean_text = self.apply_llm_response(response_text, response_actions, raw_response, speak=False)
        if not clean_text:
            logger.info("LLM response only triggered physical actions.")
            return
        if not self._is_active_request(request_id):
            return
        self._remember_person_chat(speaker, clean_text, role="assistant")
        final_lang = lang
        if detect_text_language:
            final_lang = detect_text_language(clean_text, default=lang)
        self._speak_with_mood(clean_text, language=final_lang)
        logger.info("Reply: %s", clean_text)
        self.memory.add_event(f"I replied: {clean_text}")

    def _react_to_speech(self, text: str, source_lang: str | None = None) -> None:
        """React to heard text."""
        from modules.speech.services.wake_phrase import contains_wakeword, strip_wakewords

        low = str(text or "").lower()
        has_wake = contains_wakeword(low)

        request_id = uuid.uuid4().hex[:10]
        with self._speech_req_lock:
            self._active_speech_req_id = request_id
            self._speech_busy = True

        logger.info("Heard: %s", text)
        self.state["last_interaction"] = time.time()
        lang = str(source_lang or self.state.get("last_speech_language") or "tr")

        if self._handle_barge_in_and_wakeword(text, low, has_wake, request_id):
            return

        if self._handle_speech_command_shortcuts(text, lang, request_id):
            return

        speaker = self._process_speech_social_context(text)

        if self._handle_blocked_or_special_commands(text, speaker, lang):
            return

        if self._handle_offline_mode(text, lang):
            return

        try:
            if self._try_agent_core_path(text, lang, speaker, request_id):
                return
            self._try_direct_llm_path(text, lang, speaker, request_id)
        except Exception as exc:
            logger.error("Failed to generate reply: %s", exc)
            self.appraise_event("command_failed", emit=False)
            self.client.push_interaction_event("error", {"source": "ollama", "reason": "chat_failed"})
            self._apply_emotion_visual_state("fear")
        finally:
            with self._speech_req_lock:
                if self._active_speech_req_id == request_id:
                    self._speech_busy = False

    def _is_active_request(self, request_id: str) -> bool:
        with self._speech_req_lock:
            return self._active_speech_req_id == request_id

    def _apply_interaction_feedback(self, event: str, speaker: str, text: str) -> None:
        try:
            self.feedback_learner.apply(event, speaker, text=text)
        except Exception:
            pass

    def _remember_person_chat(self, speaker: str | None, text: str, role: str) -> None:
        person = str(speaker or "").strip()
        if not person or person.lower() == "unknown" or not text:
            return
        try:
            self.relationship_memory.add_chat(name=person, role=role, text=text)
        except Exception:
            pass
        try:
            self.client.append_person_chat(person=person, text=text, role=role)
        except Exception:
            pass

    def _enrich_user_text_with_companion_context(self, text: str, speaker: str | None) -> str:
        raw = str(text or "").strip()
        spk = str(speaker or "").strip()
        if not raw or not spk:
            return raw
        profile = self.relationship_memory.social_profile(spk)
        if not profile:
            return raw
        likes = profile.get("likes", []) if isinstance(profile.get("likes", []), list) else []
        topics = profile.get("topics", []) if isinstance(profile.get("topics", []), list) else []
        top_memory = str(profile.get("top_memory", "")).strip()
        hints = []
        trust = float(profile.get("trust_score", 0.0) or 0.0)
        if trust >= 0.7:
            hints.append("trust=high")
        elif trust <= 0.3:
            hints.append("trust=low")
        if likes:
            hints.append(f"likes={','.join([str(x) for x in likes[:3]])}")
        if topics:
            hints.append(f"topics={','.join([str(x) for x in topics[:3]])}")
        recalled = ""
        try:
            from .recall import most_relevant

            candidates = self.relationship_memory.recall_candidates(spk)
            recalled = most_relevant(raw, candidates) or ""
        except Exception:
            recalled = ""
        if recalled:
            hints.append(f"recall={recalled[:90]}")
        elif top_memory:
            hints.append(f"memory={top_memory[:90]}")
        if not hints:
            return raw
        enriched = f"{raw}\n\n[CompanionContext speaker={spk}] {', '.join(hints)}"
        logger.info("Companion context injected | speaker=%s hints=%s", spk, ", ".join(hints))
        try:
            self.client.push_interaction_event("companion.context_injected", {"speaker": spk})
        except Exception:
            pass
        return enriched

    def _note_person_seen(self, name: str, emotion: str = "") -> None:
        person = str(name or "").strip()
        if not person or person.lower() == "unknown":
            return
        try:
            self.relationship_memory.observe_person(
                name=person,
                is_owner=bool(self._is_owner_name(person)) if hasattr(self, "_is_owner_name") else False,
                emotion=emotion,
            )
        except Exception:
            pass

    def _handle_follow_commands(self, text: str, speaker: str | None, language: str) -> bool:
        low = str(text or "").lower()
        stop_tokens = [
            "takibi bırak",
            "takibi birak",
            "beni takip etmeyi bırak",
            "beni takip etmeyi birak",
            "takipten çık",
            "takipten cik",
            "takibi durdur",
        ]
        start_tokens = [
            "beni takip et",
            "beni izle",
            "yüzümü takip et",
            "yuzumu takip et",
        ]

        if any(token in low for token in stop_tokens):
            result = self.client.stop_face_follow()
            ok = bool(isinstance(result, dict) and result.get("ok", False))
            message = "Yüz takibini durdurdum." if ok else "Yüz takibini şu an durduramıyorum."
            self._speak_with_mood(message, emotion="neutral", language=language)
            self.memory.add_event("Face follow stopped by voice command.")
            return True

        if any(token in low for token in start_tokens):
            target = None
            if speaker and str(speaker).strip() and str(speaker).strip().lower() != "unknown":
                target = str(speaker).strip()
            elif self.state.get("last_speaker") and str(self.state.get("last_speaker")).lower() != "unknown":
                target = str(self.state.get("last_speaker")).strip()

            result = self.client.start_face_follow(person=target)
            ok = bool(isinstance(result, dict) and result.get("ok", False))
            if ok:
                if target:
                    message = f"Tamam {target}, yüzünden takip modunu açtım."
                else:
                    message = "Yüz takibini açtım, seni kilitleyince takip edeceğim."
                self.memory.add_event(f"Face follow started. target={target or 'auto'}")
                self._speak_with_mood(message, emotion="joy", language=language)
            else:
                self._speak_with_mood("Yüz takibini şu an başlatamıyorum.", emotion="neutral", language=language)
            return True

        return False

    def _offline_reply(self, text: str, service: str) -> str:
        cfg = self.config.get("offline_mode", {})
        context = self._offline_context_label(text)
        contextual = cfg.get("contextual_replies", {}) if isinstance(cfg.get("contextual_replies", {}), dict) else {}
        ctx_pool = contextual.get(context)
        if isinstance(ctx_pool, list) and ctx_pool:
            return str(random.choice(ctx_pool))
        persona = cfg.get("persona_replies", {}) if isinstance(cfg.get("persona_replies", {}), dict) else {}
        mood_key = str(self.mood.get_dominant_emotion() or "neutral")
        mood_replies = persona.get(mood_key)
        if isinstance(mood_replies, list) and mood_replies:
            return str(random.choice(mood_replies))
        neutral_replies = persona.get("neutral")
        if isinstance(neutral_replies, list) and neutral_replies:
            return str(random.choice(neutral_replies))
        replies: List[str] = (
            cfg.get("fallback_replies", []) if isinstance(cfg.get("fallback_replies", []), list) else []
        )
        if replies:
            return str(random.choice(replies))
        if "?" in str(text):
            return "Su an baglanti yok, ama birazdan tekrar deneyebilirim."
        return f"Su an {service} ulasilamiyor, yine de buradayim."

    @staticmethod
    def _offline_context_label(text: str) -> str:
        t = str(text or "").strip().lower()
        if not t:
            return "generic"
        if "?" in t:
            return "question"
        if any(k in t for k in ["merhaba", "selam", "hey", "gunaydin", "iyi aksamlar"]):
            return "greeting"
        if any(k in t for k in ["yap", "ac", "kapat", "calistir", "dur", "git", "don"]):
            return "command"
        return "generic"

    def apply_llm_response(
        self,
        text: str,
        actions: dict | None = None,
        raw_text: str | None = None,
        speak: bool = False,
    ) -> str:
        """Harici modüllerin persona etiketlerini işletmesine izin ver."""
        clean = self._handle_llm_actions(text or "", actions, raw_text)
        if speak and clean:
            self._speak_with_mood(clean)
        return clean
