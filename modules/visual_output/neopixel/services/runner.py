from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any, Optional

try:
    from .driver import NeoDriver, NeoDriverConfig
    from .animations import (
        rainbow as anim_rainbow,
        rainbow_cycle,
        spinner as anim_spinner,
        breathe as anim_breathe,
        meteor_rain,
        fire_flicker,
        comet as anim_comet,
        wave as anim_wave,
        pulse as anim_pulse,
        twinkle as anim_twinkle,
        color_wipe,
        random_blink,
        theater_chase as anim_theater_chase,
        eye_eyebrow,
        snow as anim_snow,
        alternating_colors,
        multi_color_gradient,
        multi_color_wave,
        gradient_fade,
        bouncing_ball,
        running_lights,
        stacked_bars,
    )
except Exception:
    from driver import NeoDriver, NeoDriverConfig  # type: ignore

from .runner_presets import RunnerPresetsMixin
from .runner_companion import RunnerCompanionMixin
from .runner_adapters import _SegmentView, _AnimationCancelled, _AnimationDriver


class NeoRunner(RunnerPresetsMixin, RunnerCompanionMixin):
    def __init__(
        self,
        cfg: NeoDriverConfig,
        segments: list[dict[str, Any]] | None = None,
        presets: dict[str, Any] | None = None,
        preset_store_path: str | None = None,
        preset_version: int = 1,
        companion_cfg: dict[str, Any] | None = None,
    ):
        self.driver = NeoDriver(cfg)
        self._frame_lock = threading.RLock()
        self._animation_lock = threading.Lock()
        self._animation_generation = 0
        self._active_animation = ""
        self._companion = None
        if isinstance(companion_cfg, dict) and bool(companion_cfg.get("enabled", True)):
            try:
                from .companion_leds import CompanionLedController

                self._companion = CompanionLedController(
                    self.driver,
                    companion_cfg,
                    frame_lock=self._frame_lock,
                )
            except Exception:
                self._companion = None
        self._emotion_store = None
        self._segments: dict[str, tuple[int, int]] = {}
        self._presets: dict[str, Any] = presets if isinstance(presets, dict) else {}
        self._preset_store_path = Path(preset_store_path).resolve() if preset_store_path else None
        self._preset_version = max(1, int(preset_version or 1))
        self._init_segments(segments or [])
        self._animate_queue: queue.Queue = queue.Queue()
        self._animate_worker = threading.Thread(
            target=self._animate_worker_loop,
            name="NeoRunnerAnimate",
            daemon=True,
        )
        self._animate_worker.start()

    def _drain_animate_queue(self) -> None:
        try:
            while True:
                self._animate_queue.get_nowait()
                self._animate_queue.task_done()
        except queue.Empty:
            pass

    def _cancel_animations(self) -> int:
        with self._animation_lock:
            self._animation_generation += 1
            generation = self._animation_generation
        self._drain_animate_queue()
        return generation

    def _animation_is_current(self, generation: int) -> bool:
        with self._animation_lock:
            current = generation == self._animation_generation
        return current and not self.companion_is_active()

    def _wait_for_animations(self, timeout: float = 5.0) -> bool:
        try:
            self._animate_queue.join()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        try:
            self.companion_set_mode("off")
            self.clear()
        except Exception:
            pass

    def clear(self) -> bool:
        if self.companion_is_active():
            return False
        self._cancel_animations()
        with self._frame_lock:
            self.driver.clear()
        return True

    def fill(self, r: int, g: int, b: int) -> bool:
        if self.companion_is_active():
            return False
        self._cancel_animations()
        with self._frame_lock:
            self.driver.fill(r, g, b)
        return True

    def fill_segment(self, name: str, r: int, g: int, b: int) -> bool:
        if self.companion_is_active():
            return False
        bounds = self._segment_bounds(name)
        if bounds is None:
            return False
        self._cancel_animations()
        start, end = bounds
        with self._frame_lock:
            for i in range(start, end):
                self.driver.set(i, r, g, b)
            self.driver.show()
        return True

    def clear_segment(self, name: str) -> bool:
        return self.fill_segment(name, 0, 0, 0)

    def rainbow(self, wait: float = 0.02, cycles: int = 3) -> bool:
        return self.animate("RAINBOW", iterations=cycles)

    def theater_chase(
        self,
        r: int = 255,
        g: int = 0,
        b: int = 0,
        wait: float = 0.05,
        cycles: int = 10,
    ) -> bool:
        return self.animate("THEATER_CHASE", color=(r, g, b), iterations=cycles)

    def show_color(self, r: int, g: int, b: int, duration: float = 0.3, clear_after: bool = False) -> bool:
        if not self.fill(r, g, b):
            return False
        if duration > 0:
            def _clear_after():
                try:
                    time.sleep(duration)
                    if clear_after:
                        self.clear()
                except Exception:
                    pass

            t = threading.Thread(target=_clear_after, daemon=True)
            t.start()
        return True

    def _get_store(self):
        if self._emotion_store is None:
            try:
                from modules.visual_output.neopixel.emotions.loader import EmotionStore  # type: ignore
            except Exception:
                from ..emotions.loader import EmotionStore  # type: ignore
            self._emotion_store = EmotionStore()
        return self._emotion_store

    def emote_sequence(self, emotions: list[str], duration: float = 0.25) -> None:
        store = self._get_store()
        for emo in emotions:
            r, g, b = store.random_color(emo)
            self.show_color(r, g, b, duration=duration, clear_after=False)

    def _colors_from_emotions(self, emotions: list[str] | None) -> list[tuple[int, int, int]]:
        if not emotions:
            return []
        store = self._get_store()
        return [store.random_color(e) for e in emotions]

    def _animate_sync(
        self,
        name: str,
        emotions: list[str] | None = None,
        iterations: int | None = None,
        color: tuple[int, int, int] | None = None,
        segment: str | None = None,
        generation: int | None = None,
    ) -> None:
        if generation is None:
            with self._animation_lock:
                generation = self._animation_generation
        if not self._animation_is_current(generation):
            return
        animation_driver = _AnimationDriver(self, generation)
        name_lower = name.lower().strip()
        cols = self._colors_from_emotions(emotions)
        c1 = color if color is not None else (cols[0] if cols else None)

        if segment:
            bounds = self._segment_bounds(segment)
            if bounds is not None:
                start, end = bounds
                view = _SegmentView(animation_driver, start, end)
                if not self._run_named_animation(name, view, cols, c1, iterations):
                    fill = c1 if c1 is not None else (255, 255, 255)
                    view.fill(*fill)
                return

        if not self._run_named_animation(name, animation_driver, cols, c1, iterations):
            r, g, b = c1 if c1 else (255, 255, 255)
            if animation_driver.animate(name_lower, r, g, b, iterations or 0, 50):
                return
            if c1:
                animation_driver.fill(*c1)

    def _dispatch_animation(self, name: str, driver: Any, cols: list, c1: tuple | None, c2: tuple | None, iterations: int | None) -> bool:
        _ANIM_MAP = {
            "RAINBOW": lambda: anim_rainbow(driver, c1, iterations or 1),
            "RAINBOW_CYCLE": lambda: rainbow_cycle(driver, c1, iterations or 1),
            "SPINNER": lambda: anim_spinner(driver, c1 or (255, 0, 0), iterations or 1),
            "BREATHE": lambda: anim_breathe(driver, c1 or (255, 0, 0), iterations or 1),
            "METEOR": lambda: meteor_rain(driver, c1 or (255, 255, 255)),
            "FIRE": lambda: fire_flicker(driver, c1 or (255, 165, 0)),
            "COMET": lambda: anim_comet(driver, c1 or (0, 255, 255)),
            "WAVE": lambda: anim_wave(driver, c1),
            "PULSE": lambda: anim_pulse(driver, c1 or (255, 0, 127)),
            "TWINKLE": lambda: anim_twinkle(driver, c1 or (255, 255, 255)),
            "COLOR_WIPE": lambda: color_wipe(driver, c1 or (255, 0, 0)),
            "RANDOM_BLINK": lambda: random_blink(driver, c1),
            "THEATER_CHASE": lambda: anim_theater_chase(driver, c1 or (127, 127, 127)),
            "SNOW": lambda: anim_snow(driver, c1 or (255, 255, 255)),
            "ALTERNATING": lambda: alternating_colors(driver, c1 or (255, 0, 0), c2 or (0, 0, 255)),
            "GRADIENT": lambda: gradient_fade(driver, 5, c1),
            "BOUNCING_BALL": lambda: bouncing_ball(driver, c1 or (255, 0, 0)),
            "RUNNING_LIGHTS": lambda: running_lights(driver, c1 or (255, 0, 0)),
            "STACKED_BARS": lambda: stacked_bars(driver, 50, c1),
            "MULTI_GRADIENT": lambda: multi_color_gradient(driver, cols, iterations or 5) if cols else None,
            "MULTI_WAVE": lambda: multi_color_wave(driver, cols, iterations or 5) if cols else None,
            "EYE_EYEBROW": lambda: eye_eyebrow(driver, c1 or (255, 255, 255), iterations or 1),
        }
        fn = _ANIM_MAP.get(name)
        if fn is None:
            return False
        fn()
        return True

    def _run_named_animation(
        self,
        name: str,
        driver: Any,
        cols: list[tuple[int, int, int]],
        c1: tuple[int, int, int] | None,
        iterations: int | None,
    ) -> bool:
        name = name.upper()
        c2 = cols[1] if len(cols) > 1 else None
        return self._dispatch_animation(name, driver, cols, c1, c2, iterations)

    def _animate_worker_loop(self) -> None:
        while True:
            item = self._animate_queue.get()
            try:
                with self._animation_lock:
                    self._active_animation = str(item[0])
                self._animate_sync(*item)
            except _AnimationCancelled:
                pass
            except Exception:
                pass
            finally:
                with self._animation_lock:
                    self._active_animation = ""
                self._animate_queue.task_done()

    def animate(
        self,
        name: str,
        emotions: list[str] | None = None,
        iterations: int | None = None,
        color: tuple[int, int, int] | None = None,
        segment: str | None = None,
        *,
        coalesce: bool = True,
    ) -> bool:
        if self.companion_is_active():
            return False
        if coalesce:
            generation = self._cancel_animations()
        else:
            with self._animation_lock:
                generation = self._animation_generation
        payload = (name, emotions, iterations, color, segment, generation)
        try:
            self._animate_queue.put_nowait(payload)
            return True
        except Exception:
            try:
                self._animate_sync(*payload)
                return True
            except Exception:
                return False
