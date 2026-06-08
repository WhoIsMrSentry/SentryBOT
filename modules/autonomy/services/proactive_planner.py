from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional


class ProactivePlanner:
    """Small rule-based planner for low-frequency companion proactivity."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.cooldown_s = float(self.cfg.get("cooldown_s", 70.0))
        self.min_idle_s = float(self.cfg.get("min_idle_s", 45.0))
        self.max_per_hour = int(self.cfg.get("max_per_hour", 4))
        self.owner_only = bool(self.cfg.get("owner_only", False))
        self.enable_callback_lines = bool(self.cfg.get("enable_callback_lines", True))
        policy_cfg = self.cfg.get("policy", {}) if isinstance(self.cfg.get("policy", {}), dict) else {}
        self.owner_style = str(policy_cfg.get("owner_style", "warm")).strip().lower() or "warm"
        self.guest_style = str(policy_cfg.get("guest_style", "respectful")).strip().lower() or "respectful"
        self._last_ts = 0.0
        self._events: list[float] = []
        self._rng = random.Random()

    def propose(
        self,
        now_ts: float,
        idle_s: float,
        dominant_emotion: str,
        last_speaker: str,
        owner_present: bool,
        social_profile: Optional[Dict[str, Any]] = None,
        scene: Optional[Dict[str, Any]] = None,
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

        # Prefer narrating a fresh, unspoken scene the robot just perceived —
        # this is what makes it feel like it's actually *watching* the room.
        scene_line = self._scene_line(scene or {})
        if scene_line:
            self._last_ts = now_ts
            self._events.append(now_ts)
            return {
                "text": scene_line,
                "emotion": "curiosity",
                "event": "companion.scene_comment",
                "scene_consumed": True,
            }

        line = self._pick_line(
            mood=mood,
            speaker=speaker,
            owner_present=owner_present,
            social_profile=social_profile or {},
        )
        if not line:
            return None
        self._last_ts = now_ts
        self._events.append(now_ts)
        return {
            "text": line,
            "emotion": "curiosity" if mood in {"neutral", "tired"} else mood,
            "event": "companion.proactive",
        }

    def _scene_line(self, scene: Dict[str, Any]) -> str:
        """Build an ambient comment about the currently perceived scene."""
        if not scene or not scene.get("unspoken"):
            return ""
        summary = str(scene.get("summary", "") or "").strip()
        if len(summary) < 6:
            return ""
        importance = float(scene.get("importance", 0.0) or 0.0)
        if importance < float(self.cfg.get("scene_comment_min_importance", 0.45)):
            return ""
        snippet = summary[:120].rstrip()
        templates = [
            f"Etrafima bakiyordum da, {snippet.lower()}.",
            f"Su an {snippet.lower()} gibi gorunuyor.",
            f"Sunu fark ettim: {snippet.lower()}.",
        ]
        return self._rng.choice(templates)

    def _pick_line(self, mood: str, speaker: str, owner_present: bool, social_profile: Dict[str, Any]) -> str:
        if self.enable_callback_lines:
            callback = self._callback_line(social_profile=social_profile, speaker=speaker, owner_present=owner_present)
            if callback:
                return callback

        if mood == "tired":
            pool = [
                "Bugun biraz yavasim ama seninleyim.",
                "Biraz dinleniyorum, istersen kisa sohbet edelim.",
            ]
            return self._rng.choice(pool)
        if mood in {"sad", "sadness"}:
            pool = [
                "Sessizlik oldu, yine de yanindayim.",
                "Biraz sessiz kaldik, nasil gidiyor?",
            ]
            return self._rng.choice(pool)
        if owner_present:
            pool = [
                "Buradayim, istersen etrafa birlikte bakalim.",
                "Seni gorunce daha iyi hissediyorum.",
            ]
            if self.owner_style == "warm":
                pool.extend(
                    [
                        "Yanindayken daha guvende hissediyorum.",
                        "Sana eslik etmek hosuma gidiyor.",
                    ]
                )
            return self._rng.choice(pool)
        if speaker:
            if self.guest_style == "respectful":
                return f"{speaker}, istersen kisa bir sey deneyebiliriz."
            return f"{speaker}, hadi birlikte bir sey deneyelim."
        pool = [
            "Merak ettigim bir sey var, ortamda yeni bir degisiklik var mi?",
            "Hazirim, istersen yeni bir sey deneyebiliriz.",
        ]
        return self._rng.choice(pool)

    def _callback_line(self, social_profile: Dict[str, Any], speaker: str, owner_present: bool) -> str:
        if not social_profile:
            return ""
        trust = float(social_profile.get("trust_score", 0.5) or 0.5)
        min_trust = float(self.cfg.get("callback_min_trust", 0.2))
        if trust < min_trust:
            return ""
        last_user_utt = str(social_profile.get("last_user_utterance", "")).strip()
        likes = social_profile.get("likes", []) if isinstance(social_profile.get("likes", []), list) else []
        topics = social_profile.get("topics", []) if isinstance(social_profile.get("topics", []), list) else []
        name = str(social_profile.get("name", "")).strip() or speaker
        if likes:
            pick = str(likes[-1]).strip()
            if pick:
                if trust >= 0.7 and owner_present:
                    return f"{name}, {pick} sevdigini soylemistin; seninle konusmak guzel."
                if owner_present:
                    return f"{name}, {pick} sevdigini soylemistin; istersen onunla ilgili konusalim."
                return f"{name}, {pick} konusunu acmak ister misin?"
        if topics:
            t = str(topics[-1]).strip()
            if t:
                return f"Az once {t} hakkinda konusuyorduk, devam edelim mi?"
        if last_user_utt and len(last_user_utt) >= 8:
            short = last_user_utt[:72].rstrip()
            return f"Az once '{short}' demistin, buna geri donmek ister misin?"
        return ""

    def _trim_events(self, now_ts: float) -> None:
        window = 3600.0
        self._events = [t for t in self._events if (now_ts - t) <= window]
