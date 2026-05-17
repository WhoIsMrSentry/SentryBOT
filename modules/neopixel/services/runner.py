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


class NeoRunner:
    def __init__(
        self,
        cfg: NeoDriverConfig,
        segments: list[dict[str, Any]] | None = None,
        presets: dict[str, Any] | None = None,
        preset_store_path: str | None = None,
        preset_version: int = 1,
    ):
        self.driver = NeoDriver(cfg)
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
        return self._segments.get(str(name).strip().lower())

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

        # Segment target currently supports deterministic color output.
        if segment:
            if c1 is None:
                c1 = (255, 255, 255)
            if self.fill_segment(segment, *c1):
                return

        name = name.upper()
        c2 = cols[1] if len(cols) > 1 else None
        # Map names to functions
        if name == "RAINBOW":
            anim_rainbow(self.driver, c1, iterations or 1)
        elif name == "RAINBOW_CYCLE":
            rainbow_cycle(self.driver, c1, iterations or 1)
        elif name == "SPINNER":
            anim_spinner(self.driver, c1 or (255, 0, 0), iterations or 1)
        elif name == "BREATHE":
            anim_breathe(self.driver, c1 or (255, 0, 0), iterations or 1)
        elif name == "METEOR":
            meteor_rain(self.driver, c1 or (255, 255, 255))
        elif name == "FIRE":
            fire_flicker(self.driver, c1 or (255, 165, 0))
        elif name == "COMET":
            anim_comet(self.driver, c1 or (0, 255, 255))
        elif name == "WAVE":
            anim_wave(self.driver, c1)
        elif name == "PULSE":
            anim_pulse(self.driver, c1 or (255, 0, 127))
        elif name == "TWINKLE":
            anim_twinkle(self.driver, c1 or (255, 255, 255))
        elif name == "COLOR_WIPE":
            color_wipe(self.driver, c1 or (255, 0, 0))
        elif name == "RANDOM_BLINK":
            random_blink(self.driver, c1)
        elif name == "THEATER_CHASE":
            anim_theater_chase(self.driver, c1 or (127, 127, 127))
        elif name == "SNOW":
            anim_snow(self.driver, c1 or (255, 255, 255))
        elif name == "ALTERNATING":
            alternating_colors(self.driver, c1 or (255, 0, 0), c2 or (0, 0, 255))
        elif name == "GRADIENT":
            gradient_fade(self.driver, 5, c1)
        elif name == "BOUNCING_BALL":
            bouncing_ball(self.driver, c1 or (255, 0, 0))
        elif name == "RUNNING_LIGHTS":
            running_lights(self.driver, c1 or (255, 0, 0))
        elif name == "STACKED_BARS":
            stacked_bars(self.driver, 50, c1)
        elif name == "MULTI_GRADIENT":
            if cols:
                multi_color_gradient(self.driver, cols, iterations or 5)
        elif name == "MULTI_WAVE":
            if cols:
                multi_color_wave(self.driver, cols, iterations or 5)
        else:
            # Unknown animation name: try backend-native animation first.
            r, g, b = c1 if c1 else (255, 255, 255)
            if self.driver.animate(name_lower, r, g, b, iterations or 0, 50):
                return
            # last-resort fallback simple fill
            if c1:
                self.fill(*c1)

    def _animate_worker_loop(self) -> None:
        while True:
            item = self._animate_queue.get()
            try:
                self._animate_sync(*item)
            except Exception:
                pass
            finally:
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
    ) -> None:
        """Queue animations so only one runs at a time; drop pending when coalesce=True."""
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
