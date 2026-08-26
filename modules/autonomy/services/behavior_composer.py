"""BehaviorComposer — Composes holistic, multi-modal actions from free-form LLM plans.

Translates an autonomous thought-plan into coordinated physical primitives:
- Expression: Face/OLED + LED lighting effects + emotional tone
- Non-verbal audio: Cute/emotional sound catalog (CUTE_SOUND_CATALOG)
- Verbal audio: TTS speech with dynamic prosody
- Posture & Attention: Pan/tilt gaze & saccades
- Locomotion: Clamped safe navigation to free space / rest corner
- State: Pose lock and conditional wake-up (wake_when)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.behavior_composer")


class BehaviorComposer:
    """Orchestrates atomic execution of multi-modal autonomous behavior packages."""

    def __init__(self, brain: Any = None, client: Any = None) -> None:
        self.brain = brain
        self.client = client
        self._lock = threading.RLock()
        self._active_plan: Optional[Dict[str, Any]] = None
        self._pose_locked: bool = False
        self._pose_lock_until: float = 0.0
        self._wake_condition: Optional[Dict[str, Any]] = None

    def set_brain(self, brain: Any) -> None:
        with self._lock:
            self.brain = brain
            if not self.client and hasattr(brain, "client"):
                self.client = brain.client

    def is_pose_locked(self, now: Optional[float] = None) -> bool:
        """Check if autonomous pose lock is currently active."""
        ts = now if now is not None else time.time()
        with self._lock:
            if not self._pose_locked:
                return False
            if ts >= self._pose_lock_until:
                self._pose_locked = False
                self._wake_condition = None
                return False
            return True

    def check_wake_condition(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Check incoming sensory events against the active wake_when trigger."""
        with self._lock:
            if not self._pose_locked or not self._wake_condition:
                return False

            cond = self._wake_condition
            event_clean = str(event_type).strip().lower()

            # Person enters / spotted
            if cond.get("person_enters") and ("person" in event_clean or "face" in event_clean):
                self._release_pose_lock("person_entered")
                return True

            # Audio threshold
            if "audio_above" in cond and "audio" in event_clean:
                vol = float((data or {}).get("volume", 0.0))
                if vol >= float(cond["audio_above"]):
                    self._release_pose_lock("loud_audio")
                    return True

            # Generic event match
            if cond.get("event") and cond["event"] == event_clean:
                self._release_pose_lock(f"event_{event_clean}")
                return True

            return False

    def _release_pose_lock(self, reason: str) -> None:
        logger.info(f"Releasing behavior pose lock (reason={reason})")
        self._pose_locked = False
        self._pose_lock_until = 0.0
        self._wake_condition = None
        if self.brain and hasattr(self.brain, "appraise_event"):
            self.brain.appraise_event("woken_by_stimulus", emit=False)

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically execute a free-form behavior plan across all modalities."""
        if not isinstance(plan, dict):
            return {"status": "error", "message": "plan must be a dictionary"}

        results: Dict[str, Any] = {"status": "executed", "components": {}}
        now = time.time()

        with self._lock:
            self._active_plan = dict(plan)

            # 1. Thought / Memory
            thought = str(plan.get("thought") or "").strip()
            if thought and self.brain and hasattr(self.brain, "memory"):
                try:
                    self.brain.memory.add_event(f"I thought: {thought}")
                    results["components"]["thought"] = thought
                except Exception as exc:
                    logger.debug("Failed recording thought into memory: %s", exc)

            # 2. Emotion & Lighting (Face, OLED, LEDs)
            emotion = plan.get("emotion")
            if isinstance(emotion, dict) or isinstance(emotion, str):
                emo_label = emotion.get("label") if isinstance(emotion, dict) else str(emotion)
                duration = float(emotion.get("duration_s", 15.0)) if isinstance(emotion, dict) else 15.0
                intensity = float(emotion.get("intensity", 0.8)) if isinstance(emotion, dict) else 0.8
                try:
                    if self.client and hasattr(self.client, "express_emotion"):
                        self.client.express_emotion(
                            emotion=emo_label,
                            intensity=intensity,
                            duration=duration,
                            source="behavior_composer",
                        )
                    results["components"]["emotion"] = emo_label
                except Exception as exc:
                    logger.warning("BehaviorComposer emotion dispatch failed: %s", exc)

            lights = plan.get("lights")
            if isinstance(lights, dict) and self.client:
                effect = lights.get("effect_hint", "breathe")
                palette = lights.get("palette_hint", "neutral")
                try:
                    if hasattr(self.client, "set_neopixel"):
                        self.client.set_neopixel(
                            mode=effect,
                            emotions=[palette],
                            duration=float(lights.get("duration_s", 10.0)),
                        )
                    results["components"]["lights"] = {"effect": effect, "palette": palette}
                except Exception as exc:
                    logger.debug("BehaviorComposer lights dispatch failed: %s", exc)

            # 3. Non-Verbal Audio (CUTE_SOUND_CATALOG / EMOTION_TO_CUTE)
            vocal_sound = plan.get("vocal_sound")
            if vocal_sound and self.client:
                sound_name = str(vocal_sound).strip().lower()
                try:
                    # Attempt via cute_sound action or play_emotion
                    if hasattr(self.client, "queue_action"):
                        self.client.queue_action(
                            "cute_sound",
                            priority=65,
                            payload={"sound": sound_name, "mode": "play_emotion"},
                        )
                    results["components"]["vocal_sound"] = sound_name
                except Exception as exc:
                    logger.debug("BehaviorComposer vocal_sound dispatch failed: %s", exc)

            # 4. Verbal Speech (TTS)
            say = plan.get("say")
            if say and self.brain:
                text = say.get("text") if isinstance(say, dict) else str(say)
                tone = say.get("tone_hint") if isinstance(say, dict) else None
                if text and hasattr(self.brain, "_speak_with_mood"):
                    try:
                        self.brain._speak_with_mood(text, emotion=tone)
                        results["components"]["say"] = {"text": text, "tone": tone}
                    except Exception as exc:
                        logger.warning("BehaviorComposer speech dispatch failed: %s", exc)

            # 5. Posture & Head Gaze
            posture = plan.get("posture")
            look = plan.get("look")
            if (posture or look) and self.client:
                head_payload: Dict[str, Any] = {}
                if isinstance(posture, dict):
                    if "head_tilt" in posture:
                        head_payload["tilt"] = int(posture["head_tilt"])
                    if "eyes" in posture and hasattr(self.client, "set_face_state"):
                        try:
                            self.client.set_face_state(posture["eyes"])
                        except Exception:
                            pass
                if isinstance(look, dict):
                    if "pan" in look:
                        head_payload["pan"] = int(look["pan"])
                    elif "angle_deg" in look:
                        head_payload["pan"] = int(look["angle_deg"])

                if head_payload and hasattr(self.client, "queue_action"):
                    try:
                        self.client.queue_action("head_move", priority=70, payload=head_payload)
                        results["components"]["head"] = head_payload
                    except Exception as exc:
                        logger.debug("BehaviorComposer head dispatch failed: %s", exc)

            # 6. Locomotion & Navigation
            move = plan.get("move")
            if move and self.brain and hasattr(self.brain, "execute_safe_rest_corner"):
                target = move.get("target") if isinstance(move, dict) else str(move)
                try:
                    logger.info(f"BehaviorComposer executing move target: {target}")
                    self.brain.execute_safe_rest_corner()
                    results["components"]["move"] = target
                except Exception as exc:
                    logger.warning("BehaviorComposer move dispatch failed: %s", exc)

            # 7. Learned Macro Replay
            macro_name = plan.get("replay_macro") or plan.get("macro")
            if macro_name and self.brain and hasattr(self.brain, "shadow_learner"):
                try:
                    ok = self.brain.shadow_learner.replay_macro(str(macro_name), self.client)
                    if ok:
                        results["components"]["replay_macro"] = str(macro_name)
                except Exception as m_exc:
                    logger.debug("Failed replaying macro in BehaviorComposer: %s", m_exc)

            # 8. Wake Condition & Pose Lock
            wake_when = plan.get("wake_when")
            if wake_when and isinstance(wake_when, dict):
                lock_duration = float(plan.get("duration_s", 60.0))
                self._pose_locked = True
                self._pose_lock_until = now + lock_duration
                self._wake_condition = wake_when
                results["components"]["wake_when"] = wake_when
                results["components"]["pose_lock_s"] = lock_duration

        return results


__all__ = ["BehaviorComposer"]
