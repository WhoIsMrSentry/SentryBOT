from __future__ import annotations
import time

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
    def __init__(self, cfg: NeoDriverConfig):
        self.driver = NeoDriver(cfg)
        # Emotions loader is optional; imported lazily to avoid cost
        self._emotion_store = None

    # Exposed operations
    def clear(self) -> None:
        self.driver.clear()

    def fill(self, r: int, g: int, b: int) -> None:
        self.driver.fill(r, g, b)

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
        self.fill(r, g, b)
        if duration > 0:
            time.sleep(duration)
        if clear_after:
            self.clear()

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

    def animate(
        self,
        name: str,
        emotions: list[str] | None = None,
        iterations: int | None = None,
        color: tuple[int, int, int] | None = None,
    ) -> None:
        name = name.upper()
        cols = self._colors_from_emotions(emotions)
        c1 = color if color is not None else (cols[0] if cols else None)
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
            # fallback simple fill
            if c1:
                self.fill(*c1)
