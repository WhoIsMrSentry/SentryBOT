"""Needs/mood-driven companion line generation with optional LLM."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.companion_lines")


class CompanionLineGenerator:
    """Generate short proactive/ritual lines from internal state (+ optional LLM)."""

    def __init__(self, client: Any, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg if isinstance(cfg, dict) else {}
        self.client = client
        self.use_llm = bool(cfg.get("use_llm", True))
        self.max_words = int(cfg.get("max_words", 18))
        self.llm_cooldown_s = float(cfg.get("llm_cooldown_s", 35.0))
        self.default_language = str(cfg.get("default_language", "tr"))
        self._last_llm_ts = 0.0

    def generate(self, kind: str, **ctx: Any) -> Optional[str]:
        """Return a short companion utterance or ``None`` to use template fallback."""
        if self.use_llm and self._llm_allowed():
            line = self._llm_line(kind, ctx)
            if line:
                return line
        return self._needs_line(kind, ctx)

    def _llm_allowed(self) -> bool:
        return (time.time() - self._last_llm_ts) >= self.llm_cooldown_s

    def _llm_line(self, kind: str, ctx: Dict[str, Any]) -> Optional[str]:
        if self.client is None or not hasattr(self.client, "chat"):
            return None
        prompt = self._build_prompt(kind, ctx)
        lang = str(ctx.get("language") or self.default_language)
        try:
            resp = self.client.chat(prompt, response_lang=lang)
            if isinstance(resp, dict) and resp.get("ok") is False:
                self._last_llm_ts = time.time()
                logger.info(
                    "companion LLM unavailable; using template fallback: %s",
                    resp.get("error") or resp.get("reason") or "unavailable",
                )
                return None
            text = ""
            if isinstance(resp, dict):
                text = str(resp.get("answer") or resp.get("text") or "").strip()
            if not text:
                return None
            words = text.split()
            if len(words) > self.max_words:
                text = " ".join(words[: self.max_words])
            self._last_llm_ts = time.time()
            return text
        except Exception as exc:
            self._last_llm_ts = time.time()
            logger.debug("companion LLM line failed: %s", exc)
            return None

    @staticmethod
    def _build_prompt(kind: str, ctx: Dict[str, Any]) -> str:
        mood = str(ctx.get("dominant_emotion") or "neutral")
        needs = ctx.get("needs") or {}
        speaker = str(ctx.get("speaker") or "").strip()
        owner = bool(ctx.get("owner_present"))
        scene = str(ctx.get("scene_summary") or "").strip()[:100]
        social = str(ctx.get("social_hint") or "").strip()[:80]
        absence = int(float(ctx.get("absence_s") or 0))

        base = (
            f"You are a companion robot. Speak ONE short sentence ({kind}). "
            f"Mood={mood}. Needs: social={needs.get('social', '?')}, "
            f"stimulation={needs.get('stimulation', '?')}, rest={needs.get('rest', '?')}. "
        )
        if speaker:
            base += f"Speaker={speaker}. "
        if owner:
            base += "Owner is present. "
        if scene:
            base += f"Scene: {scene}. "
        if social:
            base += f"Memory: {social}. "
        if absence > 0:
            base += f"Owner was away {absence}s. "
        base += "No markdown, no quotes, max 18 words, natural and warm."
        return base

    @staticmethod
    def _needs_line(kind: str, ctx: Dict[str, Any]) -> Optional[str]:
        needs = ctx.get("needs") or {}
        social = float(needs.get("social", 0) or 0)
        stim = float(needs.get("stimulation", 0) or 0)
        rest = float(needs.get("rest", 100) or 100)
        mood = str(ctx.get("dominant_emotion") or "neutral")
        speaker = str(ctx.get("speaker") or "").strip()
        scene = str(ctx.get("scene_summary") or "").strip()

        social_hint = str(ctx.get("social_hint") or "").strip()
        if social_hint.startswith("likes "):
            pick = social_hint.replace("likes ", "", 1).strip()
            if pick:
                return f"{speaker + ', ' if speaker else ''}{pick} hakkında konuşalım mı?"
        if social_hint.startswith("topic "):
            pick = social_hint.replace("topic ", "", 1).strip()
            if pick:
                return f"{speaker + ', ' if speaker else ''}{pick} ile ilgili bir şey söyleyeyim mi?"

        if kind == "scene" and scene:
            return f"Şunu fark ettim: {scene[:90].rstrip()}."
        if kind == "ritual_morning":
            return "Günaydın, bugün nasıl hissediyorsun?"
        if kind == "ritual_owner_return":
            return "Tekrar hoş geldin, seni görmek iyi geldi."
        if social >= 70:
            return f"{speaker + ', ' if speaker else ''}biraz sohbet etmek ister misin?"
        if stim >= 75:
            return "Canım sıkıldı, birlikte bir şey deneyelim mi?"
        bat = float(ctx.get("battery_pct", 100) or 100)
        cpu = float(ctx.get("cpu_temp", 45) or 45)
        if bat < 15:
            return "Pilim çok azaldı, biraz dinlenmeye ve şarja ihtiyacım var."
        if cpu > 75:
            return "İşlemcim çok ısındı, biraz sakin kalıp soğumaya ihtiyacım var."
        if rest >= 70 or rest <= 25:
            return "Biraz dinlenmeye ihtiyacım var, bugün çok enerji harcadım."
        if mood in {"sad", "sadness"}:
            return "Sessizlik oldu, yine de yanınızdayım."
        if bool(ctx.get("owner_present")):
            return "Buradayım, istersen etrafa birlikte bakalım."
        return "Merak ediyorum, ortamda yeni bir şey var mı?"


__all__ = ["CompanionLineGenerator"]
