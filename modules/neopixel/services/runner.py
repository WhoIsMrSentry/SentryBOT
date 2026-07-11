from __future__ import annotations
import queue
import threading
import time
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from .driver import NeoDriver, NeoDriverConfig
    from .effects import wheel
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
    from effects import wheel  # type: ignore


class _SegmentView:
    """Adapter that exposes a driver sub-range as if it were a full strip.

    Lets the existing whole-strip animation functions run on a single
    segment without modifying them: index ``i`` is remapped to
    ``start + i`` and out-of-range writes are ignored.
    """

    def __init__(self, driver: Any, start: int, end: int) -> None:
        self._driver = driver
        self._start = start
        self._end = end
        self.num_leds = max(0, end - start)

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self._driver.set(self._start + idx, r, g, b)

    def show(self) -> None:
        self._driver.show()

    def clear(self) -> None:
        for i in range(self._start, self._end):
            self._driver.set(i, 0, 0, 0)
        self._driver.show()

    def fill(self, r: int, g: int, b: int) -> None:
        for i in range(self._start, self._end):
            self._driver.set(i, r, g, b)
        self._driver.show()


class NeoRunner:
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
        self._companion = None
        if isinstance(companion_cfg, dict) and bool(companion_cfg.get("enabled", True)):
            try:
                from .companion_leds import CompanionLedController

                self._companion = CompanionLedController(self.driver, companion_cfg)
            except Exception:
                self._companion = None
        # Emotions loader is optional; imported lazily to avoid cost
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

    def _init_segments(self, segments: list[dict[str, Any]]) -> None:
        for item in segments:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if not name:
                continue
            start = int(item.get("start", 0))
            count = int(item.get("count", 0))
            if count <= 0:
                continue
            end = start + count
            start = max(0, min(self.driver.num_leds, start))
            end = max(start, min(self.driver.num_leds, end))
            if end > start:
                self._segments[name] = (start, end)

    def list_segments(self) -> list[dict[str, int | str]]:
        out = []
        for name, (start, end) in sorted(self._segments.items()):
            out.append({"name": name, "start": start, "count": end - start})
        return out

    def list_presets(self) -> list[str]:
        return sorted([str(k) for k in self._presets.keys()])

    def preset_version(self) -> int:
        return int(self._preset_version)

    def get_preset(self, name: str) -> dict[str, Any] | None:
        raw = self._presets.get(str(name))
        if isinstance(raw, dict):
            return dict(raw)
        return None

    def set_preset(self, name: str, spec: dict[str, Any], persist: bool = True) -> bool:
        key = str(name or "").strip()
        if not key or not isinstance(spec, dict):
            return False
        self._presets[key] = dict(spec)
        if persist:
            self._persist_presets()
        return True

    def delete_preset(self, name: str, persist: bool = True) -> bool:
        key = str(name or "").strip()
        if not key or key not in self._presets:
            return False
        del self._presets[key]
        if persist:
            self._persist_presets()
        return True

    def _persist_presets(self) -> bool:
        if self._preset_store_path is None:
            return False
        try:
            data: dict[str, Any] = {}
            if self._preset_store_path.exists():
                with open(self._preset_store_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                data = {}
            self._preset_version += 1
            meta = data.get("presets_meta") if isinstance(data.get("presets_meta"), dict) else {}
            meta["version"] = self._preset_version
            data["presets_meta"] = meta
            data["presets"] = dict(self._presets)
            self._preset_store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._preset_store_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=False)
            return True
        except Exception:
            return False

    def _segment_bounds(self, name: str | None) -> tuple[int, int] | None:
        if not name:
            return None
        key = str(name).strip().lower()
        bounds = self._segments.get(key)
        if bounds is not None:
            return bounds
        aliases = {"jewel": "head", "stick": "body", "head": "jewel", "body": "stick"}
        alt = aliases.get(key)
        if alt:
            return self._segments.get(alt)
        return None

    def _drain_animate_queue(self) -> None:
        try:
            while True:
                self._animate_queue.get_nowait()
                self._animate_queue.task_done()
        except queue.Empty:
            pass

    def _wait_for_animations(self, timeout: float = 5.0) -> bool:
        """Wait for all queued animations to complete. Returns True if completed, False on timeout."""
        try:
            self._animate_queue.join()
            return True
        except Exception:
            return False

    # Exposed operations
    def clear(self) -> None:
        self._drain_animate_queue()
        self.driver.clear()

    def fill(self, r: int, g: int, b: int) -> None:
        self._drain_animate_queue()
        self.driver.fill(r, g, b)

    def fill_segment(self, name: str, r: int, g: int, b: int) -> bool:
        bounds = self._segment_bounds(name)
        if bounds is None:
            return False
        start, end = bounds
        for i in range(start, end):
            self.driver.set(i, r, g, b)
        self.driver.show()
        return True

    def clear_segment(self, name: str) -> bool:
        return self.fill_segment(name, 0, 0, 0)

    @staticmethod
    def _parse_color(raw: Any) -> tuple[int, int, int] | None:
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                return (int(raw[0]) & 255, int(raw[1]) & 255, int(raw[2]) & 255)
            except Exception:
                return None
        if isinstance(raw, str):
            s = raw.strip()
            if s.startswith("#") and len(s) >= 7:
                try:
                    v = int(s[1:7], 16)
                    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
                except Exception:
                    return None
        return None

    def apply_preset(self, name: str) -> bool:
        preset = self._presets.get(str(name))
        if not isinstance(preset, dict):
            return False
        for seg_name, spec in preset.items():
            if not isinstance(spec, dict):
                continue
            color = self._parse_color(spec.get("color"))
            effect = spec.get("effect")
            if isinstance(effect, str) and effect:
                self.animate(effect, color=color, segment=str(seg_name))
                continue
            if color is not None:
                self.fill_segment(str(seg_name), color[0], color[1], color[2])
        return True

    def rainbow(self, wait: float = 0.02, cycles: int = 3) -> None:
        n = self.driver.num_leds
        for j in range(256 * cycles):
            for i in range(n):
                r, g, b = wheel((i * 256 // n + j) & 255)
                self.driver.set(i, r, g, b)
            self.driver.show()
            time.sleep(wait)

    def theater_chase(self, r: int = 255, g: int = 0, b: int = 0, wait: float = 0.05, cycles: int = 10) -> None:
        n = self.driver.num_leds
        for _ in range(cycles):
            for phase in range(3):
                for i in range(n):
                    if (i + phase) % 3 == 0:
                        self.driver.set(i, r, g, b)
                    else:
                        self.driver.set(i, 0, 0, 0)
                self.driver.show()
                time.sleep(wait)

    # --- Emotions ---
    def show_color(self, r: int, g: int, b: int, duration: float = 0.3, clear_after: bool = False) -> None:
        # Immediate visual update; do not block the caller waiting for duration.
        self.fill(r, g, b)
        if duration > 0:
            import threading

            def _clear_after():
                try:
                    time.sleep(duration)
                    if clear_after:
                        self.clear()
                except Exception:
                    pass

            t = threading.Thread(target=_clear_after, daemon=True)
            t.start()

    def _get_store(self):
        if self._emotion_store is None:
            try:
                from modules.neopixel.emotions.loader import EmotionStore  # type: ignore
            except Exception:
                from ..emotions.loader import EmotionStore  # type: ignore
            self._emotion_store = EmotionStore()
        return self._emotion_store

    def emote_sequence(self, emotions: list[str], duration: float = 0.25) -> None:
        store = self._get_store()
        for emo in emotions:
            r, g, b = store.random_color(emo)
            self.show_color(r, g, b, duration=duration, clear_after=False)

    # --- Animations ---
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
    ) -> None:
        """Synchronous implementation of animation (may block)."""
        name_lower = name.lower().strip()
        cols = self._colors_from_emotions(emotions)
        c1 = color if color is not None else (cols[0] if cols else None)

        # Segment target: run the *actual* animation scoped to the segment's
        # LED range (falling back to a solid fill for that segment only).
        if segment:
            bounds = self._segment_bounds(segment)
            if bounds is not None:
                start, end = bounds
                view = _SegmentView(self.driver, start, end)
                if not self._run_named_animation(name, view, cols, c1, iterations):
                    fill = c1 if c1 is not None else (255, 255, 255)
                    view.fill(*fill)
                return
            # Unknown segment name: degrade to whole-strip behaviour below.

        if not self._run_named_animation(name, self.driver, cols, c1, iterations):
            # Unknown animation name: try backend-native animation first.
            r, g, b = c1 if c1 else (255, 255, 255)
            if self.driver.animate(name_lower, r, g, b, iterations or 0, 50):
                return
            # last-resort fallback simple fill
            if c1:
                self.fill(*c1)

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
                self._animate_sync(*item)
            except Exception:
                pass
            finally:
                self._animate_queue.task_done()

    def companion_set_mode(self, mode: str) -> bool:
        if self._companion is None:
            return False
        if str(mode or "").strip().lower() not in {"", "off"}:
            self._drain_animate_queue()
        self._companion.set_mode(mode)
        return True

    def companion_set_vu_level(self, level: float, *, right: Optional[float] = None) -> bool:
        if self._companion is None:
            return False
        self._companion.set_vu_level(level, right=right)
        return True

    def companion_is_active(self) -> bool:
        if self._companion is None:
            return False
        return self._companion.is_active

    def companion_set_eye_color(self, r: int, g: int, b: int) -> bool:
        if self._companion is None:
            return False
        self._companion.set_eye_color((int(r) & 255, int(g) & 255, int(b) & 255))
        return True

    def companion_status(self) -> dict[str, Any]:
        if self._companion is None:
            return {"enabled": False, "mode": "off"}
        return {"enabled": True, "mode": self._companion.mode}

    def animate(
        self,
        name: str,
        emotions: list[str] | None = None,
        iterations: int | None = None,
        color: tuple[int, int, int] | None = None,
        segment: str | None = None,
        *,
        coalesce: bool = True,
    ) -> None:
        """Queue animations so only one runs at a time; drop pending when coalesce=True."""
        if self.companion_is_active():
            return
        payload = (name, emotions, iterations, color, segment)
        if coalesce:
            try:
                while True:
                    self._animate_queue.get_nowait()
                    self._animate_queue.task_done()
            except queue.Empty:
                pass
        try:
            self._animate_queue.put_nowait(payload)
        except Exception:
            try:
                self._animate_sync(*payload)
            except Exception:
                pass
