from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, List

try:
    from modules.voice.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None

from modules.common.persona_scope import get_active_persona_meta

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

    def _speak_with_mood(
        self,
        text: str,
        emotion: str | None = None,
        language: str | None = None,
        voice: str | None = None,
    ) -> None:
        if not text:
            return
        state_lang = str((getattr(self, "state", None) or {}).get("last_speech_language") or "tr")
        if not language and detect_text_language:
            language = detect_text_language(text, default=state_lang)
        elif not language:
            language = state_lang
        if not voice:
            meta = get_active_persona_meta()
            if isinstance(meta, dict):
                v = str(meta.get("tts_voice") or "").strip()
                if v and v.lower() not in {"auto", "none", "null"}:
                    voice = v
                elif str(language).lower() == "en":
                    ve = str(meta.get("tts_voice_en") or "").strip()
                    if ve and ve.lower() not in {"auto", "none", "null"}:
                        voice = ve
        tone = self._tone_profile(emotion)
        payload: Dict[str, Any] = {
            "text": text,
            "tone": tone,
            "language": language,
        }
        if voice:
            payload["voice"] = str(voice).strip()
        try:
            self.client.queue_action("speak", priority=50, ttl_ms=10000, payload=payload)
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

    def _should_skip_sound_llm(self, now: float) -> bool:
        """Avoid letting sound_detected background turns starve active user speech."""
        behaviors_cfg = self.config.get("behaviors") if isinstance(getattr(self, "config", None), dict) else None
        curiosity_cfg = behaviors_cfg.get("curiosity") if isinstance(behaviors_cfg, dict) else None
        if (
            isinstance(curiosity_cfg, dict)
            and "sound_llm_enabled" in curiosity_cfg
            and not bool(curiosity_cfg.get("sound_llm_enabled"))
        ):
            return True
        if bool(getattr(self, "_speech_busy", False)) or self._robot_is_speaking():
            return True
        if bool(getattr(getattr(self, "agent", None), "is_busy", False)):
            return True
        last_speech_ts = float(self.state.get("last_speech_time", 0.0) or 0.0)
        if last_speech_ts > 0.0 and (now - last_speech_ts) < 6.0:
            return True
        checker = getattr(getattr(self, "client", None), "is_wakeword_window_active", None)
        if callable(checker):
            try:
                if bool(checker(recent_s=6.0)):
                    return True
            except Exception:
                pass
        return False

    def _react_to_sound(self, angle: float) -> None:
        now = time.time()
        last_reaction = float(self.state.get("last_sound_reaction_time", 0.0) or 0.0)
        if (now - last_reaction) < 12.0:
            return
        self.state["last_sound_reaction_time"] = now
        logger.info("Sound detected at %s", angle)
        # Anlık İşitsel Kulak Refleksi (Pi GPIO 12 & 13)
        try:
            self.client.queue_action("piservo_reflex", priority=90, payload={"angle": float(angle)})
        except Exception:
            pass
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

        if self._should_skip_sound_llm(now):
            logger.debug("Skipping sound_detected LLM step during active speech/agent turn")
            return

        ollama_ready = True
        if getattr(self, "client", None) and hasattr(self.client, "is_service_available"):
            try:
                ollama_ready = bool(self.client.is_service_available("ollama"))
            except Exception:
                ollama_ready = True

        if ollama_ready and getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
            prompt = (
                f"You just heard a sudden sound from angle {int(angle)} degrees. "
                f"Your head turned toward it (pan={int(target_pan)}). "
                f"React naturally - express curiosity, surprise, or caution. "
                f"Use your physical tools (express_emotion, move_head, look_around, speak). "
                f"Do not ask for permission."
            )
            trace_id = f"sound_{int(time.time())}"
            if hasattr(self, "_dispatch_agent_step_event"):
                self._dispatch_agent_step_event("sound_detected", prompt, trace_id=trace_id)
            else:
                try:
                    self.agent.step_event("sound_detected", prompt, trace_id=trace_id)
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
