from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from ..appraisal_triggers import speech_appraisal_event

logger = logging.getLogger("autonomy")

try:
    from modules.voice.speak.services.lang_detect import detect_text_language
except ImportError:
    detect_text_language = None


class SpeechReactMixin:
    """Speech reaction, emotion command parsing, and appraisal triggers."""

    config: Dict[str, Any]
    state: Dict[str, Any]
    mood: Any
    memory: Any
    client: Any
    _speech_min_interval_s: float

    _EMOTION_COMMAND_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("anger", ("sinirlen", "kız", "kızgın ol", "öfkelen", "sinirlensene")),
        ("joy", ("mutlu ol", "sevin", "gülümse", "neşelen", "mutlu görün")),
        ("sadness", ("üzül", "hüzünlen", "üzgün ol")),
        ("fear", ("kork", "korkmuş gibi yap", "ürper")),
        ("surprise", ("şaşır", "şaşkın ol")),
        ("bored", ("sıkıl", "ofla", "canın sıkılsın")),
        ("tired", ("yorul", "esne", "uykulu ol")),
        ("love", ("sev beni", "tatlı ol", "şirin ol")),
        ("excitement", ("heyecanlan", "coş")),
        ("neutral", ("sakinleş", "normale dön", "düz dur", "nötr ol")),
    )

    def on_speech_final(self, text: str, source_lang: str | None = None, ts: float = 0.0) -> None:
        if not text or not text.strip():
            return
        t = text.strip()
        last_ts = float(self.state.get("last_speech_ts", 0.0) or 0.0)
        
        if ts > 0.0 and ts == last_ts:
            return
            
        last_text = str(self.state.get("last_speech_text") or "").strip()
        now = time.time()
        if t == last_text and (now - float(self.state.get("last_speech_time", 0.0) or 0.0)) < self._speech_min_interval_s:
            logger.debug("Suppressing duplicate speech delivery within debounce window: %s", t)
            return
        self.state["last_speech_text"] = t
        self.state["last_speech_time"] = now
        self.state["last_speech_ts"] = ts
        self._dispatch_final_speech(t, source_lang=source_lang)

    def _dispatch_final_speech(self, text: str, source_lang: str | None = None) -> None:
        self.interaction_occurred("speech")
        detected_lang = source_lang
        if detect_text_language:
            text_lang = detect_text_language(text, default=source_lang or "tr")
            if text_lang:
                detected_lang = text_lang
        if not detected_lang:
            detected_lang = "tr"
        self.state["last_speech_language"] = detected_lang
        try:
            self.client.push_interaction_event("speech.final", {"text": text, "lang": detected_lang})
            self.client.set_oled_stt_text(text)
        except Exception:
            pass
        self._react_to_speech(text, source_lang=detected_lang)

    @staticmethod
    def _sentiment_event_for_text(text: str) -> str | None:
        return speech_appraisal_event(text)

    def _maybe_emit_speech_excited(self, text: str, sentiment_event: str | None) -> None:
        reactions_cfg = self.config.get("speech_reactions", {}) if isinstance(self.config.get("speech_reactions"), dict) else {}
        t = str(text or "")
        if reactions_cfg:
            excited_on_speech = bool(reactions_cfg.get("excited_on_speech", False))
            excited_on_praise = bool(reactions_cfg.get("excited_on_praise", False))
            excited_on_questions = bool(reactions_cfg.get("excited_on_questions", False))

            if excited_on_speech:
                self.client.push_interaction_event("autonomy.excited")
                return
            if excited_on_praise and sentiment_event in {"user_praise", "praise", "owner_returned"}:
                self.client.push_interaction_event("autonomy.excited")
                return
            if excited_on_questions and "?" in t:
                self.client.push_interaction_event("autonomy.excited")
                return
            return

        positive_sentiment = sentiment_event in {"praise", "user_praise", "owner_returned"}
        exclaimed = "!" in t or positive_sentiment
        if not exclaimed:
            return
        energy = float(self.mood.state.get("energy", 50.0) or 50.0)
        happiness = float(self.mood.state.get("happiness", 50.0) or 50.0)
        if (energy + happiness) >= 110.0:
            self.client.push_interaction_event("speech.excited", {"text": t, "energy": energy, "happiness": happiness})

    @classmethod
    def _emotion_command_for_text(cls, text: str) -> str | None:
        low = str(text or "").lower().strip(" .!?")
        if not low:
            return None
        words = low.split()
        if len(words) > 2:
            return None
        for canon, phrases in cls._EMOTION_COMMAND_PHRASES:
            for phrase in phrases:
                p = phrase.strip().lower()
                if low == p or (len(words) == 1 and words[0] == p.split()[0]):
                    return canon
        if len(words) == 1:
            try:
                from modules.common.emotion_vocab import get_vocab
                canon = get_vocab().canonical(words[0])
                if canon not in {"neutral", "curiosity"}:
                    return canon
            except Exception:
                pass
        return None

    @staticmethod
    def _emotion_command_reply(canon: str, lang: str) -> str:
        tr_replies = {
            "anger": "Tamam, sinirliyim! Ne istiyorsun?",
            "furious": "Çok sinirliyim! Dikkat et!",
            "joy": "Harika, mutluyum!",
            "sadness": "Tamam... biraz üzgünüm.",
            "fear": "Korkuyorum...",
            "surprise": "Vay! Şaşırdım!",
            "bored": "Sıkıldım galiba.",
            "tired": "Yorgunum...",
            "love": "Seni de seviyorum!",
            "excitement": "Heyecanlandım!",
            "confusion": "Kafam karıştı...",
            "worried": "Biraz endişeliyim.",
            "curiosity": "Merak ettim!",
            "neutral": "Tamam.",
        }
        en_replies = {
            "anger": "Fine, I'm angry! What do you want?",
            "furious": "I'm furious! Watch out!",
            "joy": "I'm happy!",
            "neutral": "Okay.",
        }
        replies = tr_replies if str(lang or "tr").startswith("tr") else en_replies
        return replies.get(str(canon or "neutral"), replies.get("neutral", "Okay."))

    def _handle_emotion_command(self, text: str, lang: str) -> bool:
        cmd = self._emotion_command_for_text(text)
        if not cmd:
            return False
        mood_axis = {
            "anger": "anger",
            "furious": "anger",
            "joy": "happiness",
            "fear": "fear",
            "sadness": "sadness",
            "excitement": "happiness",
            "love": "happiness",
        }
        axis = mood_axis.get(cmd)
        if axis:
            self.mood.modify(axis, 40)
        reply = self._emotion_command_reply(cmd, lang)
        canon = self.express(cmd, say=reply, language=lang)
        self.state["last_emotion"] = canon
        self.client.update_emotions([canon])
        visual = self._normalize_emotion_name(canon)
        try:
            self._run_scene(f"emotion_{visual}", context={"emotion": canon})
        except Exception:
            pass
        self.memory.add_event(f"User asked me to express: {cmd}")
        logger.info("Emotion command handled: %s -> %s", text, canon)
        return True
