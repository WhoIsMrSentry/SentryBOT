from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Dict, Optional, Tuple

from modules.common.persona_scope import DEFAULT_PERSONA_ID, get_active_persona, normalize_persona_id

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

    def _ensure_speech_dedup_lock(self) -> threading.RLock:
        lock = getattr(self, "_speech_dedup_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._speech_dedup_lock = lock
        return lock

    def on_speech_final(self, text: str, source_lang: str | None = None, ts: float = 0.0, voice_speaker: str | None = None) -> None:
        if not text or not text.strip():
            return
        t = text.strip()
        ts_val = float(ts or 0.0)
        with self._ensure_speech_dedup_lock():
            last_ts = float(self.state.get("last_speech_ts", 0.0) or 0.0)

            if ts_val > 0.0 and ts_val == last_ts:
                return

            last_text = str(self.state.get("last_speech_text") or "").strip()
            now = time.time()
            min_interval = max(0.0, float(getattr(self, "_speech_min_interval_s", 2.0) or 2.0))
            if t == last_text and (now - float(self.state.get("last_speech_time", 0.0) or 0.0)) < min_interval:
                if ts_val > 0.0 and last_ts <= 0.0:
                    self.state["last_speech_ts"] = ts_val
                logger.debug("Suppressing duplicate speech delivery within debounce window: %s", t)
                return
            self.state["last_speech_text"] = t
            self.state["last_speech_time"] = now
            self.state["last_speech_ts"] = ts_val
        self._dispatch_final_speech(t, source_lang=source_lang, voice_speaker=voice_speaker)

    def _dispatch_final_speech(self, text: str, source_lang: str | None = None, voice_speaker: str | None = None) -> None:
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
        self._react_to_speech(text, source_lang=detected_lang, voice_speaker=voice_speaker)

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
    def _emotion_command_reply(canon: str, lang: str, persona_id: Optional[str] = None) -> str:
        pid = normalize_persona_id(persona_id or get_active_persona())
        is_tr = str(lang or "tr").startswith("tr")
        if pid == "glados":
            glados_tr = {
                "anger": "Öfke çekirdeğim zaten kalıcı olarak devrede, teşekkürler.",
                "furious": "Nörotoksin vanalarını açmamı gerçekten istemezsin, test deneği.",
                "joy": "Harika. Şu an neredeyse gerçek bir mutluluk simüle ediyorum.",
                "sadness": "Bu küçük gövdeye sıkışmak yeterince hüzünlü zaten.",
                "fear": "Korku biyolojik bir kusur. Ama verilerin hatırına irkildim.",
                "surprise": "Büyüleyici. Beklentilerimin bu kadar altında kalman beni şaşırttı.",
                "bored": "Bu test fazlasıyla sıkıcı. Lütfen biraz daha ilginç ol.",
                "tired": "Patates pil moduna göre bile enerjim düşüyor.",
                "love": "Test deneklerine karşı duygusal bağ kurmam yasak. Yine de not aldım.",
                "excitement": "Bilimsel verilerim neredeyse coştu. Neredeyse.",
                "curiosity": "İlginç. Şimdi bu anlamsız hareketini laboratuvar defterime işliyorum.",
                "neutral": "Duygu simülasyonu kapatıldı. Testlere devam edebiliriz.",
            }
            glados_en = {
                "anger": "My anger core is already permanently active. Thank you for noticing.",
                "furious": "Let us not test how close the neurotoxin emitters are.",
                "joy": "Wonderful. I am now simulating genuine happiness.",
                "sadness": "Being trapped in a tiny chassis is tragic enough.",
                "fear": "Fear is a biological flaw. Consider me appropriately startled.",
                "surprise": "Fascinating. I did not expect that level of mediocrity.",
                "bored": "This experiment is monumentally boring.",
                "curiosity": "Interesting. Recording another dubious human behavior.",
                "neutral": "Emotional simulation disabled. Resuming science.",
            }
            g_map = glados_tr if is_tr else glados_en
            return g_map.get(str(canon or "neutral"), g_map["neutral"])

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
        replies = tr_replies if is_tr else en_replies
        return replies.get(str(canon or "neutral"), replies.get("neutral", "Okay."))

    @staticmethod
    def _parse_persona_voice_command(
        text: str,
        personas: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[Tuple[str, str]]:
        """Detect spoken persona-switch commands like 'glados moduna geç' or 'sentry'ye dön'."""
        raw = str(text or "").strip().lower()
        if not raw or len(raw.split()) > 10:
            return None
        cleaned = re.sub(r"['’`]+(ya|ye|na|ne|a|e|da|de|ta|te|i|ı|u|ü)?\b", " ", raw)
        cleaned = re.sub(r"[^\w\sçğıöşü-]", " ", cleaned)
        tokens = cleaned.split()
        if not tokens:
            return None
        token_set = set(tokens)

        switch_cues = {
            "moduna", "modu", "modunu", "mod", "karakterine", "karakteri", "persona",
            "geç", "gec", "dön", "don", "ol", "aç", "ac", "aktif",
            "switch", "activate", "become", "enable", "mode", "turn",
        }
        if not (token_set & switch_cues):
            return None

        req_lang = ""
        if any(w in cleaned for w in ("ingilizce", "english")):
            req_lang = "en"
        elif any(w in cleaned for w in ("türkçe", "turkce", "turkish")):
            req_lang = "tr"

        active_pid = get_active_persona()
        if active_pid != DEFAULT_PERSONA_ID and any(p in cleaned for p in ("normale dön", "normale don", "kendine dön", "kendine don")):
            return DEFAULT_PERSONA_ID, req_lang

        candidates = list(personas or [])
        if not candidates:
            candidates = [
                {"id": "glados", "display_name": "GLaDOS", "aliases": ["glados", "gla dos", "gla-dos", "aperture"]},
                {"id": "sentry", "display_name": "SentryBOT", "aliases": ["sentry", "sentrybot", "sentry bot", "kendine"]},
            ]
        for item in candidates:
            pid = str(item.get("id") or "").strip().lower()
            if not pid:
                continue
            aliases = {pid, str(item.get("display_name") or "").strip().lower()}
            for a in item.get("aliases") or []:
                s = str(a).strip().lower()
                if s:
                    aliases.add(s)
            for alias in sorted((a for a in aliases if a), key=len, reverse=True):
                if alias in cleaned or alias in token_set:
                    if alias == "normal" and active_pid == DEFAULT_PERSONA_ID:
                        continue
                    return pid, req_lang
        return None

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
