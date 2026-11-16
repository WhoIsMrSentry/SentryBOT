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
import time
from dataclasses import dataclass
from typing import Any

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
        self._expression_gen: int = 0

        # Transition graph covering all 29 canonical Emotion states
        self._visual_transition_graph: dict[Emotion, list[Emotion]] = {
            Emotion.NEUTRAL: [e for e in Emotion if e is not Emotion.NEUTRAL],
            Emotion.CALM: [
                Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.JOY, Emotion.SADNESS,
                Emotion.TIRED, Emotion.BORED,
            ],
            Emotion.CURIOSITY: [
                Emotion.NEUTRAL, Emotion.CALM, Emotion.JOY, Emotion.SURPRISE,
                Emotion.EXCITEMENT, Emotion.CONFUSION, Emotion.SUSPICIOUS,
            ],
            Emotion.JOY: [
                Emotion.NEUTRAL, Emotion.CALM, Emotion.LOVE, Emotion.EXCITEMENT,
                Emotion.PRIDE, Emotion.KAWAII, Emotion.COOL,
            ],
            Emotion.LOVE: [Emotion.JOY, Emotion.NEUTRAL, Emotion.CALM, Emotion.KAWAII, Emotion.EMBARRASSMENT],
            Emotion.SADNESS: [Emotion.NEUTRAL, Emotion.CALM, Emotion.WORRIED, Emotion.GLOOMY, Emotion.TIRED],
            Emotion.FEAR: [Emotion.NEUTRAL, Emotion.WORRIED, Emotion.SURPRISE, Emotion.NERVOUS],
            Emotion.ANGER: [Emotion.NEUTRAL, Emotion.FURIOUS, Emotion.SUSPICIOUS, Emotion.DEVIL],
            Emotion.FURIOUS: [Emotion.ANGER, Emotion.NEUTRAL],
            Emotion.SURPRISE: [Emotion.NEUTRAL, Emotion.AWE, Emotion.CURIOSITY, Emotion.EXCITEMENT, Emotion.FEAR],
            Emotion.EXCITEMENT: [Emotion.JOY, Emotion.NEUTRAL, Emotion.SURPRISE, Emotion.WIRED, Emotion.PRIDE],
            Emotion.WORRIED: [Emotion.NEUTRAL, Emotion.FEAR, Emotion.SADNESS, Emotion.NERVOUS],
            Emotion.DISGUST: [Emotion.NEUTRAL, Emotion.ANGER, Emotion.GLOOMY, Emotion.SUSPICIOUS],
            Emotion.CONFUSION: [Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.DISORIENTED, Emotion.SURPRISE],
            Emotion.BORED: [Emotion.NEUTRAL, Emotion.CALM, Emotion.CURIOSITY, Emotion.TIRED],
            Emotion.TIRED: [Emotion.NEUTRAL, Emotion.CALM, Emotion.SADNESS, Emotion.BORED],
            Emotion.PRIDE: [Emotion.NEUTRAL, Emotion.JOY, Emotion.CALM, Emotion.COOL],
            Emotion.EMBARRASSMENT: [Emotion.NEUTRAL, Emotion.CALM, Emotion.SADNESS, Emotion.NERVOUS, Emotion.LOVE],
            Emotion.AWE: [Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.JOY, Emotion.SURPRISE],
            Emotion.GLOOMY: [Emotion.NEUTRAL, Emotion.SADNESS, Emotion.CALM, Emotion.TIRED],
            Emotion.COOL: [Emotion.NEUTRAL, Emotion.CALM, Emotion.JOY, Emotion.PRIDE],
            Emotion.DEVIL: [Emotion.NEUTRAL, Emotion.ANGER, Emotion.EXCITEMENT, Emotion.COOL],
            Emotion.KAWAII: [Emotion.NEUTRAL, Emotion.JOY, Emotion.LOVE, Emotion.CALM],
            Emotion.DEAD: [Emotion.NEUTRAL, Emotion.TIRED, Emotion.SADNESS],
            Emotion.SMOKING: [Emotion.NEUTRAL, Emotion.CALM, Emotion.ANGER, Emotion.TIRED],
            Emotion.WIRED: [Emotion.NEUTRAL, Emotion.EXCITEMENT, Emotion.NERVOUS, Emotion.CALM],
            Emotion.NERVOUS: [Emotion.NEUTRAL, Emotion.WORRIED, Emotion.CALM, Emotion.FEAR],
            Emotion.DISORIENTED: [Emotion.NEUTRAL, Emotion.CONFUSION, Emotion.CURIOSITY, Emotion.CALM],
            Emotion.SUSPICIOUS: [Emotion.NEUTRAL, Emotion.CURIOSITY, Emotion.ANGER, Emotion.WORRIED],
        }

    def _evaluate_guards(
        self,
        canon: Emotion,
        raw_emotion: str | Emotion,
        now: float,
        force: bool,
    ) -> dict[str, Any] | None:
        is_emergency = str(raw_emotion).strip().lower() in {
            "error", "danger", "alert", "estop", "alarm", "emergency", "critical",
        }
        effective_force = bool(force) or is_emergency
        if effective_force:
            return None
        if now - self._last_expression[1] < self._min_interval_s:
            return {"ok": False, "reason": "rate_limited", "emotion": canon.value}
        if now < self._visual_lock_until:
            return {
                "ok": False,
                "reason": "visual_locked",
                "lock_reason": self._visual_lock_reason,
                "remaining_s": round(self._visual_lock_until - now, 1),
            }
        if self._last_expression[1] > 0.0:
            current = self._vocab.canonical(self._visual_state_emotion)
            allowed = self._visual_transition_graph.get(current, [])
            if allowed and canon != current and canon not in allowed:
                if now - self._visual_state_since < self._visual_state_hold_s:
                    return {
                        "ok": False,
                        "reason": "transition_blocked",
                        "current": current.value,
                        "allowed": [e.value for e in allowed],
                    }
        return None

    @staticmethod
    def _clamp_head_target(pan_delta: int, tilt_delta: int) -> tuple[int, int]:
        pan = max(30, min(150, 90 + int(pan_delta)))
        tilt = max(60, min(120, 90 + int(tilt_delta)))
        return pan, tilt

    async def preview_emotion(
        self,
        emotion: str | Emotion,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: list[str] | None = None,
        text: str | None = None,
        language: str = "tr",
        force: bool = False,
    ) -> dict[str, Any]:
        """Dry-run evaluation without side effects or visual-lock mutation."""
        canon = self._vocab.canonical(emotion)
        raw_render = self._vocab.render(canon)
        scaled_render = self._scale_render(raw_render, intensity)
        selected = list(modalities or ["leds", "oled", "voice", "head", "ears"])
        head_pan, head_tilt = self._clamp_head_target(
            scaled_render.head_pan_delta, scaled_render.head_tilt_delta
        )
        async with self._lock:
            now = time.time()
            blocked = self._evaluate_guards(canon, emotion, now, force)
            lock_remaining = round(max(0.0, self._visual_lock_until - now), 3)
            current_emotion = self._visual_state_emotion
        return {
            "ok": True,
            "dry_run": True,
            "would_execute": blocked is None,
            "blocked_reason": blocked.get("reason") if blocked else None,
            "blocked": blocked,
            "current_emotion": current_emotion,
            "visual_lock_remaining_s": lock_remaining,
            "emotion": canon.value,
            "intensity": intensity,
            "duration_s": duration_s,
            "modalities": selected,
            "text": text,
            "language": language,
            "head_target": {"pan": head_pan, "tilt": head_tilt},
            "render": self._render_to_dict(scaled_render),
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
        """Express a canonical emotion across all modalities atomically."""
        canon = self._vocab.canonical(emotion)
        base_render = self._vocab.render(canon)

        async with self._lock:
            now = time.time()
            blocked = self._evaluate_guards(canon, emotion, now, force)
            if blocked is not None:
                return blocked
            self._expression_gen += 1
            my_gen = self._expression_gen
            prev_task = self._active_task
            self._active_task = None

        # Cancel and await previous expression OUTSIDE self._lock so slow adapters never stall callers
        if prev_task is not None and not prev_task.done():
            prev_task.cancel()
            try:
                await asyncio.wait_for(prev_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass

        async with self._lock:
            if my_gen != self._expression_gen:
                return {"ok": False, "reason": "superseded", "emotion": canon.value}
            now = time.time()
            selected_modalities = list(modalities or ["leds", "oled", "voice", "head", "ears"])
            render = self._scale_render(base_render, intensity)
            self._active_task = asyncio.create_task(
                self._run_expression(render, duration_s, selected_modalities, text, language)
            )
            self._visual_state_emotion = canon.value
            self._visual_state_since = now
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
                "modalities": selected_modalities,
                "render": self._render_to_dict(render),
            }

    async def stop(self) -> None:
        """Cancel any active expression task and reset hardware cleanly."""
        async with self._lock:
            self._expression_gen += 1
            task = self._active_task
            self._active_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass

    async def _reset_hardware(self, modalities: list[str]) -> None:
        cleanup = []
        if "leds" in modalities and self._clients.neopixel and hasattr(self._clients.neopixel, "turn_off"):
            cleanup.append(self._clients.neopixel.turn_off())
        if "head" in modalities and self._clients.head and hasattr(self._clients.head, "move_head"):
            cleanup.append(self._clients.head.move_head(90, 90))
        if "ears" in modalities and self._clients.piservo and hasattr(self._clients.piservo, "set_ears"):
            cleanup.append(self._clients.piservo.set_ears("neutral"))
        if cleanup:
            try:
                await asyncio.gather(*cleanup, return_exceptions=True)
            except Exception:
                pass

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
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                await self._reset_hardware(modalities)
                raise

    async def _run_neopixel(self, render: EmotionRender, duration_s: float) -> None:
        """Run NeoPixel effect with random palette variant (already scaled by _scale_render)."""
        try:
            rgb = random.choice(render.neopixel_variants) if render.neopixel_variants else render.neopixel_rgb
            await self._clients.neopixel.set_effect(
                effect=render.neopixel_effect,
                color=rgb,
                speed=render.neopixel_speed,
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
            pan = 90 + int(render.head_pan_delta * random.uniform(0.8, 1.2))
            tilt = 90 + int(render.head_tilt_delta * random.uniform(0.8, 1.2))
            pan, tilt = self._clamp_head_target(pan - 90, tilt - 90)

            await self._clients.head.move_head(pan, tilt)

            if duration_s > 1.0:
                await asyncio.sleep(duration_s * 0.3)
                pan2 = max(30, min(150, pan + random.randint(-5, 5)))
                tilt2 = max(60, min(120, tilt + random.randint(-3, 3)))
                await self._clients.head.move_head(pan2, tilt2)
        except asyncio.CancelledError:
            raise
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