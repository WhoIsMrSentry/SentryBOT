"""ExpressionArbiter — Unified emotional expression coordinator.

Coordinates NeoPixel LEDs, OLED faces, TTS voice, and head servos
to produce coherent, semantically-grounded emotional expressions.

All modalities derive from the canonical EmotionVocab so the robot
expresses the SAME emotion consistently across eyes, lights, voice, body.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from modules.common.emotion_vocab import Emotion, EmotionRender, get_vocab

logger = logging.getLogger("expression.arbitrator")


@dataclass
class ModalityClients:
    """Clients for each output modality (injected at startup)."""
    neopixel: Any = None      # must have: set_effect(effect, color, speed, duration_s)
    oled: Any = None          # must have: play_animation(name, duration_s, loop)
    speak: Any = None         # must have: say(text, tone, language, pitch_shift, speed)
    head: Any = None          # must have: move_head(pan, tilt)
    piservo: Any = None       # must have: set_ears(position) or gesture(name)


class ExpressionArbiter:
    """
    Atomically coordinates multi-modal emotional expression.
    
    Usage:
        arbiter = ExpressionArbiter(clients)
        await arbiter.express_emotion(
            emotion="anger",
            intensity=1.5,
            duration_s=4.0,
            modalities=["leds", "oled", "voice", "head"],
            text="Bu beni sinir ettirdi!",
            language="tr"
        )
    """
    
    def __init__(self, clients: ModalityClients, config: dict | None = None):
        self._clients = clients
        self._config = config or {}
        self._vocab = get_vocab()
        
        self._active_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._last_expression: tuple[str, float] = ("", 0.0)  # (emotion, timestamp)
        self._min_interval_s = float(self._config.get("min_interval_s", 0.5))
        
        # Visual state hold (prevents rapid flickering between emotions)
        self._visual_lock_until: float = 0.0
        self._visual_lock_reason: str = ""
        self._visual_state_emotion: str = "neutral"
        self._visual_state_since: float = time.time()
        
        # Strong emotions that warrant longer visual hold
        self._strong_visual_emotions = {
            Emotion.FEAR, Emotion.FURIOUS, Emotion.ANGER, Emotion.SURPRISE
        }
        self._visual_lock_default_s = float(self._config.get("visual_lock_default_s", 2.2))
        self._visual_lock_strong_s = float(self._config.get("visual_lock_strong_s", 4.5))
        self._visual_state_hold_s = float(self._config.get("visual_state_hold_s", 3.0))
        
        # Transition graph (which emotions can follow which)
        self._visual_transition_graph = {
            Emotion.NEUTRAL: [Emotion.CALM, Emotion.CURIOSITY, Emotion.JOY, Emotion.SADNESS, Emotion.FEAR, Emotion.ANGER, Emotion.SURPRISE],
            Emotion.CALM: [Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.JOY, Emotion.SADNESS],
            Emotion.CURIOSITY: [Emotion.NEUTRAL, Emotion.CALM, Emotion.JOY, Emotion.SURPRISE, Emotion.EXCITEMENT],
            Emotion.JOY: [Emotion.NEUTRAL, Emotion.CALM, Emotion.LOVE, Emotion.EXCITEMENT, Emotion.PRIDE],
            Emotion.LOVE: [Emotion.JOY, Emotion.NEUTRAL, Emotion.CALM],
            Emotion.SADNESS: [Emotion.NEUTRAL, Emotion.CALM, Emotion.WORRIED, Emotion.GLOOMY],
            Emotion.FEAR: [Emotion.NEUTRAL, Emotion.WORRIED, Emotion.SURPRISE],
            Emotion.ANGER: [Emotion.NEUTRAL, Emotion.FURIOUS, Emotion.SUSPICIOUS],
            Emotion.FURIOUS: [Emotion.ANGER, Emotion.NEUTRAL],
            Emotion.SURPRISE: [Emotion.NEUTRAL, Emotion.AWE, Emotion.CURIOSITY, Emotion.EXCITEMENT],
            Emotion.EXCITEMENT: [Emotion.JOY, Emotion.NEUTRAL, Emotion.SURPRISE, Emotion.WIRED],
            Emotion.WORRIED: [Emotion.NEUTRAL, Emotion.FEAR, Emotion.SADNESS],
            Emotion.DISGUST: [Emotion.NEUTRAL, Emotion.ANGER, Emotion.GLOOMY],
            Emotion.CONFUSION: [Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.DISORIENTED],
            Emotion.BORED: [Emotion.NEUTRAL, Emotion.CALM, Emotion.CURIOSITY],
            Emotion.TIRED: [Emotion.NEUTRAL, Emotion.CALM, Emotion.SADNESS],
        }
    
    async def express_emotion(
        self,
        emotion: str | Emotion,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: list[str] | None = None,
        text: str | None = None,
        language: str = "tr",
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Express a canonical emotion across all modalities atomically.
        
        Args:
            emotion: Canonical emotion name (e.g., "anger", "joy", "curiosity")
            intensity: 0.1-2.0 (0.1=subtle, 1.0=normal, 2.0=extreme)
            duration_s: How long to hold the expression (0.5-30.0)
            modalities: Subset of ["leds", "oled", "voice", "head", "ears"]
            text: Optional text to speak (requires "voice" modality)
            language: BCP-47 language code for TTS
            force: Skip visual lock and min interval checks
        
        Returns:
            Dict with expression details and render hints used
        """
        async with self._lock:
            # Resolve canonical emotion
            canon = self._vocab.canonical(emotion)
            render = self._vocab.render(canon)
            
            now = time.time()
            
            # Emergency or critical alarms automatically bypass visual lock and rate limits
            is_emergency = (
                canon in {Emotion.FEAR, Emotion.FURIOUS, Emotion.ANGER}
                or str(emotion).strip().lower() in {"error", "danger", "alert", "estop", "alarm", "emergency", "critical"}
            )
            effective_force = force or is_emergency

            # Rate limiting (unless forced or emergency)
            if not effective_force:
                if now - self._last_expression[1] < self._min_interval_s:
                    return {"ok": False, "reason": "rate_limited", "emotion": canon.value}
                
                # Visual lock (prevents rapid emotion switching)
                if now < self._visual_lock_until:
                    return {
                        "ok": False,
                        "reason": "visual_locked",
                        "lock_reason": self._visual_lock_reason,
                        "remaining_s": round(self._visual_lock_until - now, 1),
                    }
                
                # Transition graph check
                current = self._vocab.canonical(self._visual_state_emotion)
                allowed = self._visual_transition_graph.get(current, [])
                if allowed and canon not in allowed:
                    # Allow transition only after hold time
                    if now - self._visual_state_since < self._visual_state_hold_s:
                        return {
                            "ok": False,
                            "reason": "transition_blocked",
                            "current": current.value,
                            "allowed": [e.value for e in allowed],
                        }
            
            # Cancel any active expression
            if self._active_task:
                self._active_task.cancel()
                try:
                    await self._active_task
                except asyncio.CancelledError:
                    pass
            
            # Prepare modalities
            modalities = modalities or ["leds", "oled", "voice", "head"]
            
            # Apply intensity scaling to render
            render = self._scale_render(render, intensity)
            
            # Start new expression
            self._active_task = asyncio.create_task(
                self._run_expression(render, duration_s, modalities, text, language)
            )
            
            # Update visual state tracking
            self._visual_state_emotion = canon.value
            self._visual_state_since = now
            
            # Set visual lock
            is_strong = canon in self._strong_visual_emotions
            lock_s = self._visual_lock_strong_s if is_strong else self._visual_lock_default_s
            self._visual_lock_until = max(self._visual_lock_until, now + max(0.2, lock_s * intensity))
            self._visual_lock_reason = f"emotion:{canon.value}"
            
            self._last_expression = (canon.value, now)
            
            return {
                "ok": True,
                "emotion": canon.value,
                "intensity": intensity,
                "duration_s": duration_s,
                "modalities": modalities,
                "render": self._render_to_dict(render),
            }
    
    async def _run_expression(
        self,
        render: EmotionRender,
        duration_s: float,
        modalities: list[str],
        text: str | None,
        language: str,
    ) -> None:
        """Run all modality tasks concurrently."""
        tasks = []
        
        if "leds" in modalities and self._clients.neopixel:
            tasks.append(self._run_neopixel(render, duration_s))
        
        if "oled" in modalities and self._clients.oled:
            tasks.append(self._run_oled(render, duration_s))
        
        if "head" in modalities and self._clients.head:
            tasks.append(self._run_head(render, duration_s))
        
        if "ears" in modalities and self._clients.piservo:
            tasks.append(self._run_ears(render, duration_s))
        
        if "voice" in modalities and text and self._clients.speak:
            tasks.append(self._run_voice(render, text, language))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_neopixel(self, render: EmotionRender, duration_s: float) -> None:
        """Run NeoPixel effect with random palette variant."""
        try:
            # Pick random variant for organic feel
            rgb = random.choice(render.neopixel_variants) if render.neopixel_variants else render.neopixel_rgb
            
            # Intensity affects speed (higher intensity = faster)
            speed = render.neopixel_speed * (2.0 - min(1.0, render.intensity))
            
            await self._clients.neopixel.set_effect(
                effect=render.neopixel_effect,
                color=rgb,
                speed=speed,
                duration_s=duration_s,
            )
        except Exception as e:
            logger.debug("Neopixel expression failed: %s", e)
    
    async def _run_oled(self, render: EmotionRender, duration_s: float) -> None:
        """Run OLED animation."""
        try:
            loop = duration_s > 5.0
            await self._clients.oled.play_animation(
                name=render.oled_animation,
                duration_s=duration_s,
                loop=loop,
            )
        except Exception as e:
            logger.debug("OLED expression failed: %s", e)
    
    async def _run_head(self, render: EmotionRender, duration_s: float) -> None:
        """Move head with micro-saccades for lifelike behavior."""
        try:
            pan = 90 + int(render.head_pan_delta * render.intensity * random.uniform(0.8, 1.2))
            tilt = 90 + int(render.head_tilt_delta * render.intensity * random.uniform(0.8, 1.2))
            
            # Clamp to safe ranges
            pan = max(30, min(150, pan))
            tilt = max(50, min(130, tilt))
            
            await self._clients.head.move_head(pan, tilt)
            
            # Micro-saccade after 30% of duration
            if duration_s > 1.0:
                await asyncio.sleep(duration_s * 0.3)
                pan2 = max(30, min(150, pan + random.randint(-5, 5)))
                tilt2 = max(50, min(130, tilt + random.randint(-3, 3)))
                await self._clients.head.move_head(pan2, tilt2)
        except Exception as e:
            logger.debug("Head expression failed: %s", e)
    
    async def _run_ears(self, render: EmotionRender, duration_s: float) -> None:
        """Set PiServo ear position."""
        try:
            await self._clients.piservo.set_ears(render.ears_position)
        except Exception as e:
            logger.debug("Ears expression failed: %s", e)
    
    async def _run_voice(self, render: EmotionRender, text: str, language: str) -> None:
        """Speak with emotion-appropriate voice parameters."""
        try:
            await self._clients.speak.say(
                text=text,
                tone=render.voice_tone,
                language=language,
                pitch_shift=render.voice_pitch_shift,
                speed=render.voice_speed,
            )
        except Exception as e:
            logger.debug("Voice expression failed: %s", e)
    
    def _scale_render(self, render: EmotionRender, intensity: float) -> EmotionRender:
        """Apply intensity scaling to render hints."""
        return EmotionRender(
            canonical=render.canonical,
            neopixel_effect=render.neopixel_effect,
            neopixel_rgb=render.neopixel_rgb,
            neopixel_palette=render.neopixel_palette,
            neopixel_speed=render.neopixel_speed * (2.0 - min(1.0, intensity)),
            neopixel_variants=render.neopixel_variants,
            oled_animation=render.oled_animation,
            oled_bitmap=render.oled_bitmap,
            ears_position=render.ears_position,
            head_pan_delta=int(render.head_pan_delta * intensity),
            head_tilt_delta=int(render.head_tilt_delta * intensity),
            voice_tone=render.voice_tone,
            voice_pitch_shift=render.voice_pitch_shift * intensity,
            voice_speed=render.voice_speed,
            arousal=min(1.0, render.arousal * intensity),
            valence=render.valence,
            intensity=intensity,
        )
    
    def _render_to_dict(self, render: EmotionRender) -> dict[str, Any]:
        """Convert render to dict for API response."""
        return {
            "canonical": render.canonical.value,
            "neopixel": {
                "effect": render.neopixel_effect,
                "rgb": list(render.neopixel_rgb),
                "palette": render.neopixel_palette,
                "speed": render.neopixel_speed,
                "variants": [list(v) for v in render.neopixel_variants],
            },
            "oled": {
                "animation": render.oled_animation,
                "bitmap": render.oled_bitmap,
            },
            "ears": render.ears_position,
            "head": {
                "pan_delta": render.head_pan_delta,
                "tilt_delta": render.head_tilt_delta,
            },
            "voice": {
                "tone": render.voice_tone,
                "pitch_shift": render.voice_pitch_shift,
                "speed": render.voice_speed,
            },
            "semantic": {
                "arousal": render.arousal,
                "valence": render.valence,
                "intensity": render.intensity,
            },
        }
    
    async def get_status(self) -> dict[str, Any]:
        """Get current expression status."""
        return {
            "active": self._active_task is not None and not self._active_task.done(),
            "visual_lock_active": time.time() < self._visual_lock_until,
            "visual_lock_reason": self._visual_lock_reason,
            "visual_lock_remaining_s": round(max(0, self._visual_lock_until - time.time()), 1),
            "last_emotion": self._visual_state_emotion,
            "last_expression_time": self._last_expression[1],
        }


__all__ = ["ExpressionArbiter", "ModalityClients"]