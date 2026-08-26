from __future__ import annotations

import datetime
import logging
import random
import time
from typing import Any, Dict, List, Optional

try:
    from modules.voice.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None

logger = logging.getLogger("autonomy.vocal_prosody")


class VocalProsodyMixin:
    """Tone profiles, mood speaking, sound reactions, and offline speech generation."""

    config: Dict[str, Any]
    mood: Any
    state: Dict[str, Any]
    client: Any
    memory: Any
    _speech_req_lock: Any
    _active_speech_req_id: str
    _speech_busy: bool
    barge_in: Any

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
            from modules.system_control.config_center.log_redact import redact_secrets

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
        except Exception as exc:
            logger.debug("Failed to queue speech action: %s", exc)

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
        now = time.time()
        last_reaction = float(self.state.get("last_sound_reaction_time", 0.0) or 0.0)
        if (now - last_reaction) < 12.0:
            return
        self.state["last_sound_reaction_time"] = now
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
        try:
            if getattr(self, "agent", None) and hasattr(self.agent, "speech_arbiter"):
                self.agent.speech_arbiter.interrupt_all()
            else:
                self.client.stop_speaking()
                self.client.interrupt_agent_speech()
        except Exception as exc:
            logger.debug("barge-in stop failed: %s", exc)

    def _robot_is_speaking(self) -> bool:
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
        clean = self._handle_llm_actions(text or "", actions, raw_text)
        if speak and clean:
            self._speak_with_mood(clean)
        return clean
