from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy")


class EmotionSyncMixin:
    """Emotion synchronization, visual rendering, and appraisal dispatch."""

    config: Dict[str, Any]
    state: Dict[str, Any]
    mood: Any
    client: Any
    appraisal: Any
    _last_emotion_sent: Optional[str]
    _last_emotion_sync_ts: float
    _visual_emotion_min_interval_s: float
    _visual_state_emotion: str
    _visual_state_since: float
    _visual_state_hold_s: float
    _visual_strong_emotions: set[str]
    _visual_transition_graph: Dict[str, List[str]]
    _visual_lock_until: float
    _visual_lock_reason: str
    _visual_lock_strong_s: float
    _visual_lock_default_s: float

    _STRONG_VISUAL_EMOTIONS = {"fear", "furious", "anger", "surprise"}

    def _sync_emotion(self) -> None:
        dominant = self.mood.get_dominant_emotion()
        if dominant != self.state["last_emotion"]:
            self.state["last_emotion"] = dominant
            logger.info("Emotion shifted to %s", dominant)
            self._apply_timeline_event(f"emotion_{dominant}")
            self._update_timeline_emotion(dominant)
            self.client.push_interaction_event(f"mood.{dominant}")

        now = time.time()
        with self._express_lock:
            if now - self._last_emotion_sync_ts >= self._visual_emotion_min_interval_s:
                self._last_emotion_sync_ts = now
                chosen = self._select_visual_emotion(dominant)
                if chosen != self._last_emotion_sent:
                    self._last_emotion_sent = chosen
                    send = True
                else:
                    send = False
        if now - self._last_emotion_sync_ts >= self._visual_emotion_min_interval_s and send:
            # Network call outside the lock (C3).
            self.client.update_emotions([chosen])

    @staticmethod
    def _emotion_scene_name(canon: str) -> str:
        visual = EmotionSyncMixin._normalize_emotion_name(canon)
        return f"emotion_{visual}"

    def express(
        self,
        emotion: str,
        say: str | None = None,
        duration: float = 3.0,
        scene: str | None = None,
        language: str | None = None,
    ) -> str:
        try:
            from modules.common.emotion_vocab import get_vocab

            canon = get_vocab().canonical(emotion)
        except Exception:
            canon = str(emotion or "neutral").lower()

        logger.info("Expressing emotion %s (canonical: %s)", emotion, canon)
        self._apply_emotion_visual_state(canon)
        if say:
            self._speak_with_mood(say, emotion=canon, language=language)
        scene_name = scene or self._emotion_scene_name(canon)
        try:
            self._run_scene(scene_name, context={"emotion": canon, "duration": duration})
        except Exception as exc:
            logger.debug("Scene for express failed: %s", exc)
        return canon

    def appraise_event(self, event_name: str, intensity: float = 1.0, emit: bool = True) -> bool:
        if self._companion_paused() and not self.state.get("is_sleeping"):
            return False
        result = self.appraisal.process_event(event_name, intensity=intensity)
        if not result or not result.get("matched"):
            return False
        for axis, delta in result.get("mood_deltas", {}).items():
            self.mood.modify(axis, delta)
        self.state["last_appraisal"] = result
        if emit:
            payload = {
                "event": event_name,
                "intensity": intensity,
                "deltas": result.get("mood_deltas"),
                "notes": result.get("notes"),
            }
            self.client.push_interaction_event(f"appraisal:{event_name}", payload)
        self._sync_emotion()
        return True

    def _emit_idle_visuals(self, action: str) -> None:
        key = str(action or "").strip().lower()
        if self._visual_lock_active():
            return
        neo_map = {
            "blink": "RANDOM_BLINK",
            "look_around": "COMET",
            "stretch": "WAVE",
            "bored": "PULSE",
            "monologue": "TWINKLE",
        }
        oled_anim_map = {
            "blink": "blink",
            "look_around": "scanning",
            "monologue": "thinking",
        }
        oled_bitmap_map = {
            "stretch": "look_up",
            "bored": "bored",
        }

        try:
            effect = neo_map.get(key)
            if effect:
                self.client.set_neopixel(effect)
        except Exception:
            pass

        try:
            anim = oled_anim_map.get(key)
            if anim:
                self.client.oled_anim(anim)
                return
            bmp = oled_bitmap_map.get(key)
            if bmp:
                self.client.oled_show(bmp)
        except Exception:
            pass

    @staticmethod
    def _normalize_emotion_name(emotion: str) -> str:
        e = str(emotion or "neutral").strip().lower()
        aliases = {
            "sadness": "sad",
            "anger": "angry",
            "tire": "tired",
            "anxious": "fear",
        }
        return aliases.get(e, e or "neutral")

    def _select_visual_emotion(self, dominant_emotion: str) -> str:
        with self._express_lock:
            now = time.time()
            candidate = self._normalize_emotion_name(dominant_emotion)
            current = self._normalize_emotion_name(self._visual_state_emotion)
            strong = self._visual_strong_emotions
            if not current:
                self._visual_state_emotion = candidate
                self._visual_state_since = now
                return candidate
            if candidate == current:
                return current
            if candidate in strong:
                self._visual_state_emotion = candidate
                self._visual_state_since = now
                return candidate
            if (now - self._visual_state_since) < max(0.1, self._visual_state_hold_s):
                return current
            allowed = self._visual_transition_graph.get(current, [])
            if allowed and candidate not in allowed:
                return current
            self._visual_state_emotion = candidate
            self._visual_state_since = now
            return candidate

    def _visual_lock_active(self) -> bool:
        return time.time() < float(self._visual_lock_until)

    def _apply_emotion_visual_state(self, emotion: str) -> None:
        e = str(emotion or "neutral").strip().lower()
        try:
            from modules.common.emotion_vocab import emotion_render

            render = emotion_render(e)
            canon = render.canonical
            effect = render.effect
            oled = render.oled
            color = list(render.rgb)
        except Exception:
            canon, effect, oled, color = "neutral", "BREATHE", "normal", [120, 120, 140]

        strong = canon in self._STRONG_VISUAL_EMOTIONS
        with self._express_lock:
            lock_s = self._visual_lock_strong_s if strong else self._visual_lock_default_s
            self._visual_lock_until = max(self._visual_lock_until, time.time() + max(0.2, float(lock_s)))
            self._visual_lock_reason = f"emotion:{canon}"
        expressed = self.client.express_emotion(
            canon,
            modalities=["leds", "oled", "ears"],
            duration_s=max(0.5, float(lock_s)),
        )
        if expressed and expressed.get("ok"):
            return
        try:
            self.client.set_neopixel(effect, emotions=[canon], color=color)
        except Exception:
            logger.debug("neopixel fallback after expression failed", exc_info=True)
        try:
            self.client.oled_show(oled)
        except Exception:
            logger.debug("oled fallback after expression failed", exc_info=True)

    def update_palettes(self, palettes: dict[str, list[int]]) -> None:
        """Refresh in-memory palette cache after config edits."""
        defaults = self.config.setdefault("defaults", {})
        lights = defaults.setdefault("lights", {})
        lights["palettes"] = dict(palettes)
