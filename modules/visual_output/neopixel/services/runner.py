from __future__ import annotations

import logging
import queue
import threading
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
        emotional_pulse,
    )
except Exception:
    from driver import NeoDriver, NeoDriverConfig  # type: ignore

from .runner_presets import RunnerPresetsMixin
from .runner_companion import RunnerCompanionMixin
from .runner_adapters import _SegmentView, _AnimationCancelled, _AnimationDriver

logger = logging.getLogger("neopixel.runner")

_STOP_SENTINEL = object()


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
        self._preset_io_lock = threading.Lock()
        self._clear_timer_lock = threading.Lock()
        self._clear_timer: Optional[threading.Timer] = None
        self._animation_generation = 0
        self._active_animation = ""
        self._stop_event = threading.Event()
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

    def _cancel_clear_timer(self) -> None:
        with self._clear_timer_lock:
            timer = self._clear_timer
            self._clear_timer = None
            if timer is not None:
                try:
                    timer.cancel()
                except Exception:
                    pass

    def _drain_animate_queue(self) -> None:
        try:
            while True:
                item = self._animate_queue.get_nowait()
                if item is _STOP_SENTINEL:
                    self._animate_queue.put_nowait(_STOP_SENTINEL)
                    self._animate_queue.task_done()
                    break
                self._animate_queue.task_done()
        except queue.Empty:
            pass

    def _cancel_animations(self) -> int:
        self._cancel_clear_timer()
        with self._animation_lock:
            self._animation_generation += 1
            generation = self._animation_generation
        self._drain_animate_queue()
        return generation

    def _animation_is_current(self, generation: int) -> bool:
        if self._stop_event.is_set():
            return False
        with self._animation_lock:
            current = generation == self._animation_generation
        return current and not self.companion_is_active()

    def _wait_for_animations(self, timeout: float = 5.0) -> bool:
        try:
            self._animate_queue.join()
            return True
        except Exception:
            return False

    def stop(self, *, clear: bool = True) -> None:
        self._stop_event.set()
        self._cancel_animations()
        try:
            if self._companion is not None:
                self._companion.stop()
        except Exception as exc:
            logger.debug("Companion stop failed: %s", exc)
        if clear:
            try:
                with self._frame_lock:
                    self.driver.clear()
            except Exception:
                pass
        worker = self._animate_worker
        if worker and worker.is_alive():
            try:
                self._animate_queue.put_nowait(_STOP_SENTINEL)
            except Exception:
                pass
            worker.join(timeout=1.5)

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
        ranges = self._segment_ranges(name)
        if not ranges:
            return False
        self._cancel_animations()
        with self._frame_lock:
            for start, end in ranges:
                for i in range(start, end):
                    self.driver.set(i, r, g, b)
            self.driver.show()
        return True

    def clear_segment(self, name: str) -> bool:
        return self.fill_segment(name, 0, 0, 0)

    def rainbow(self, wait: float = 0.02, cycles: int = 3) -> bool:
        return self.animate("RAINBOW", iterations=cycles, wait=wait)

    def theater_chase(
        self,
        r: int = 255,
        g: int = 0,
        b: int = 0,
        wait: float = 0.05,
        cycles: int = 10,
    ) -> bool:
        return self.animate("THEATER_CHASE", color=(r, g, b), iterations=cycles, wait=wait)

    def show_color(self, r: int, g: int, b: int, duration: float = 0.3, clear_after: bool = False) -> bool:
        if not self.fill(r, g, b):
            return False
        with self._animation_lock:
            gen = self._animation_generation
        if clear_after and duration > 0:
            def _clear_after() -> None:
                if self._stop_event.is_set() or self.companion_is_active():
                    return
                with self._animation_lock:
                    if gen != self._animation_generation:
                        return
                self.clear()

            timer = threading.Timer(float(duration), _clear_after)
            timer.name = "NeoShowColorClear"
            timer.daemon = True
            with self._clear_timer_lock:
                self._clear_timer = timer
            timer.start()
        return True

    def _get_store(self):
        if self._emotion_store is None:
            try:
                from modules.visual_output.neopixel.emotions.loader import get_shared_store  # type: ignore
            except Exception:
                from ..emotions.loader import get_shared_store  # type: ignore
            self._emotion_store = get_shared_store()
        return self._emotion_store

    def emote_sequence(self, emotions: list[str], duration: float = 0.25) -> None:
        if not emotions:
            return
        store = self._get_store()
        hold_s = max(0.0, float(duration))
        for idx, emo in enumerate(emotions):
            if self._stop_event.is_set():
                break
            r, g, b = store.random_color(emo)
            is_last = idx == len(emotions) - 1
            self.show_color(r, g, b, duration=hold_s, clear_after=is_last and hold_s > 0.0)
            if not is_last and hold_s > 0.0:
                self._stop_event.wait(timeout=hold_s)

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
        wait: float | None = None,
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
                if not self._run_named_animation(name, view, cols, c1, iterations, wait=wait):
                    if c1 is not None:
                        view.fill(*c1)
                return

        if not self._run_named_animation(name, animation_driver, cols, c1, iterations, wait=wait):
            r, g, b = c1 if c1 else (255, 255, 255)
            with self._frame_lock:
                hw_ok = self.driver.animate(name_lower, r, g, b, iterations or 0, 50)
            if hw_ok:
                return
            if c1:
                animation_driver.fill(*c1)

    def _dispatch_animation(
        self,
        name: str,
        driver: Any,
        cols: list,
        c1: tuple | None,
        c2: tuple | None,
        iterations: int | None,
        wait: float | None = None,
    ) -> bool:
        multi_cols = cols if cols else ([c1] if c1 is not None else [])
        grad_cols = (
            cols
            if len(cols) >= 2
            else ([c1, (c1[0] // 3, c1[1] // 3, c1[2] // 3)] if c1 is not None else [])
        )
        wait_rb = 0.02 if wait is None else max(0.0, float(wait))
        wait_chase = 0.05 if wait is None else max(0.0, float(wait))
        stick_spans = None
        if self._segments:
            spans = [
                (s, e - s)
                for seg_k, (s, e) in sorted(self._segments.items())
                if seg_k.startswith("stick")
            ]
            if spans and getattr(driver, "num_leds", 0) >= self.driver.num_leds:
                stick_spans = spans

        _ANIM_MAP = {
            "RAINBOW": lambda: anim_rainbow(driver, c1, iterations or 1, wait=wait_rb),
            "RAINBOW_CYCLE": lambda: rainbow_cycle(driver, c1, iterations or 1, wait=wait_rb),
            "SPINNER": lambda: anim_spinner(driver, c1 or (255, 0, 0), iterations or 1),
            "BREATHE": lambda: anim_breathe(driver, c1 or (255, 0, 0), iterations or 1),
            "METEOR": lambda: meteor_rain(driver, c1 or (255, 255, 255)),
            "FIRE": lambda: fire_flicker(driver, c1 or (255, 165, 0)),
            "COMET": lambda: anim_comet(driver, c1 or (0, 255, 255)),
            "WAVE": lambda: anim_wave(driver, c1),
            "PULSE": lambda: anim_pulse(driver, c1 or (255, 0, 127)),
            "TWINKLE": lambda: anim_twinkle(driver, c1 or (255, 255, 255)),
            "WIPE": lambda: color_wipe(driver, c1 or (255, 0, 0)),
            "COLOR_WIPE": lambda: color_wipe(driver, c1 or (255, 0, 0)),
            "BLINK": lambda: random_blink(driver, c1),
            "RANDOM_BLINK": lambda: random_blink(driver, c1),
            "CHASE": lambda: anim_theater_chase(
                driver, c1 or (127, 127, 127), wait=wait_chase, cycles=iterations or 5
            ),
            "THEATER_CHASE": lambda: anim_theater_chase(
                driver, c1 or (127, 127, 127), wait=wait_chase, cycles=iterations or 5
            ),
            "SNOW": lambda: anim_snow(driver, c1 or (255, 255, 255)),
            "ALT": lambda: alternating_colors(driver, c1 or (255, 0, 0), c2 or (0, 0, 255)),
            "ALTERNATING": lambda: alternating_colors(driver, c1 or (255, 0, 0), c2 or (0, 0, 255)),
            "GRADIENT": lambda: gradient_fade(driver, iterations or 5, c1),
            "BOUNCE": lambda: bouncing_ball(driver, c1 or (255, 0, 0)),
            "BOUNCING_BALL": lambda: bouncing_ball(driver, c1 or (255, 0, 0)),
            "RUN": lambda: running_lights(driver, c1 or (255, 0, 0)),
            "RUNNING_LIGHTS": lambda: running_lights(driver, c1 or (255, 0, 0)),
            "STACK": lambda: stacked_bars(driver, 50, c1),
            "STACKED_BARS": lambda: stacked_bars(driver, 50, c1),
            "EYE_EYEBROW": lambda: eye_eyebrow(driver, c1 or (255, 255, 255), iterations or 1, sticks=stick_spans),
            "EMOTIONAL_PULSE": lambda: emotional_pulse(driver, c1 or (0, 180, 255), iterations=iterations or 1),
        }
        if name in {"M_GRAD", "MULTI_GRADIENT"}:
            if not grad_cols:
                return False
            multi_color_gradient(driver, grad_cols, iterations or 5)
            return True
        if name in {"M_WAVE", "MULTI_WAVE"}:
            if not multi_cols:
                return False
            multi_color_wave(driver, multi_cols, iterations or 5)
            return True
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
        wait: float | None = None,
    ) -> bool:
        name = name.upper()
        c2 = cols[1] if len(cols) > 1 else None
        return self._dispatch_animation(name, driver, cols, c1, c2, iterations, wait=wait)

    def _animate_worker_loop(self) -> None:
        while True:
            item = self._animate_queue.get()
            if item is _STOP_SENTINEL:
                self._animate_queue.task_done()
                break
            try:
                with self._animation_lock:
                    self._active_animation = str(item[0])
                self._animate_sync(*item)
            except _AnimationCancelled:
                pass
            except Exception as exc:
                logger.exception("Animation worker failed for '%s': %s", item[0], exc)
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
        wait: float | None = None,
    ) -> bool:
        if self.companion_is_active():
            return False
        if coalesce:
            generation = self._cancel_animations()
        else:
            with self._animation_lock:
                generation = self._animation_generation
        payload = (name, emotions, iterations, color, segment, generation, wait)
        try:
            self._animate_queue.put_nowait(payload)
            return True
        except Exception:
            try:
                self._animate_sync(*payload)
                return True
            except Exception:
                return False
