from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .companion_lines import CompanionLineGenerator


class ProactivePlanner:
    """Needs-driven companion proactivity with optional LLM line generation."""

    def __init__(self, cfg: Dict[str, Any], line_generator: Any = None) -> None:
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.cooldown_s = float(self.cfg.get("cooldown_s", 70.0))
        self.min_idle_s = float(self.cfg.get("min_idle_s", 45.0))
        self.max_per_hour = int(self.cfg.get("max_per_hour", 4))
        self.owner_only = bool(self.cfg.get("owner_only", False))
        self._line_generator = line_generator or CompanionLineGenerator(None, {"use_llm": False})
        self._last_ts = 0.0
        self._events: list[float] = []

    def propose(
        self,
        now_ts: float,
        idle_s: float,
        dominant_emotion: str,
        last_speaker: str,
        owner_present: bool,
        social_profile: Optional[Dict[str, Any]] = None,
        scene: Optional[Dict[str, Any]] = None,
        needs: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        if idle_s < self.min_idle_s:
            return None
        if (now_ts - self._last_ts) < self.cooldown_s:
            return None
        if self.owner_only and not owner_present:
            return None
        self._trim_events(now_ts)
        if len(self._events) >= self.max_per_hour:
            return None

        mood = str(dominant_emotion or "neutral").strip().lower()
        speaker = str(last_speaker or "").strip()
        needs_map = needs if isinstance(needs, dict) else {}
        profile = social_profile or {}

        scene_line = self._scene_line(scene or {}, mood=mood, needs=needs_map, speaker=speaker, owner_present=owner_present)
        if scene_line:
            self._stamp(now_ts)
            return {
                "text": scene_line,
                "emotion": "curiosity",
                "event": "companion.scene_comment",
                "scene_consumed": True,
            }

        line = self._generate_line(
            kind="proactive",
            mood=mood,
            speaker=speaker,
            owner_present=owner_present,
            needs=needs_map,
            social_profile=profile,
        )
        if not line:
            return None
        self._stamp(now_ts)
        emotion = "curiosity" if mood in {"neutral", "tired"} else mood
        return {"text": line, "emotion": emotion, "event": "companion.proactive"}

    def _generate_line(
        self,
        kind: str,
        mood: str,
        speaker: str,
        owner_present: bool,
        needs: Dict[str, Any],
        social_profile: Dict[str, Any],
    ) -> str:
        social_hint = ""
        likes = social_profile.get("likes", []) if isinstance(social_profile.get("likes", []), list) else []
        topics = social_profile.get("topics", []) if isinstance(social_profile.get("topics", []), list) else []
        dislikes = social_profile.get("dislikes", []) if isinstance(social_profile.get("dislikes", []), list) else []
        trust = float(social_profile.get("trust_score", 0.5) or 0.5)
        min_trust = float(self.cfg.get("callback_min_trust", 0.2))
        if trust >= min_trust:
            if likes:
                social_hint = f"likes {likes[-1]}"
            elif topics:
                social_hint = f"topic {topics[-1]}"
        if dislikes and trust >= min_trust:
            ctx_dislikes = ", ".join(str(x) for x in dislikes[:2])
            social_hint = (social_hint + f"; avoid {ctx_dislikes}").strip("; ").strip()
        ctx = {
            "dominant_emotion": mood,
            "speaker": speaker,
            "owner_present": owner_present,
            "needs": needs,
            "social_hint": social_hint,
        }
        if self._line_generator is not None and hasattr(self._line_generator, "generate"):
            line = self._line_generator.generate(kind, **ctx)
            if line:
                return line
        if self._line_generator is not None and hasattr(self._line_generator, "_needs_line"):
            return self._line_generator._needs_line(kind, ctx) or ""
        return ""

    def _scene_line(self, scene: Dict[str, Any], mood: str, needs: Dict[str, Any], speaker: str, owner_present: bool) -> str:
        if not scene or not scene.get("unspoken"):
            return ""
        summary = str(scene.get("summary", "") or "").strip()
        if len(summary) < 6:
            return ""
        importance = float(scene.get("importance", 0.0) or 0.0)
        if importance < float(self.cfg.get("scene_comment_min_importance", 0.45)):
            return ""
        if self._line_generator is not None and hasattr(self._line_generator, "generate"):
            line = self._line_generator.generate(
                "scene",
                dominant_emotion=mood,
                scene_summary=summary,
                needs=needs,
                speaker=speaker,
                owner_present=owner_present,
            )
            if line:
                return line
        return f"Şunu fark ettim: {summary[:100].rstrip()}."

    def _stamp(self, now_ts: float) -> None:
        self._last_ts = now_ts
        self._events.append(now_ts)

    def _trim_events(self, now_ts: float) -> None:
        window = 3600.0
        self._events = [t for t in self._events if (now_ts - t) <= window]
