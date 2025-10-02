from __future__ import annotations
import math
import random
import time
from typing import Iterable, List, Sequence, Tuple

try:
    from .driver import NeoDriver
    from .effects import wheel as base_wheel
except Exception:
    from driver import NeoDriver  # type: ignore
    from effects import wheel as base_wheel  # type: ignore

Color = Tuple[int, int, int]


def _clamp(x: float, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, int(x)))


def _wheel_tinted(pos: int, color: Color | None = None) -> Color:
    pos &= 255
    if color:
        r, g, b = color
        max_ch = max(r, g, b)
        ratio = pos / 255.0
        if max_ch == r:
            return (r, _clamp(g * ratio), 0)
        elif max_ch == g:
            return (_clamp(r * ratio), g, 0)
        else:
            return (0, _clamp(g * ratio), b)
    return base_wheel(pos)


def rainbow(driver: NeoDriver, color: Color | None = None, iterations: int = 1, wait: float = 0.02) -> None:
    n = driver.num_leds
    for j in range(256 * max(1, iterations)):
        for i in range(n):
            r, g, b = _wheel_tinted((i + j) & 255, color)
            driver.set(i, r, g, b)
        driver.show()
        time.sleep(wait)


def rainbow_cycle(driver: NeoDriver, color: Color | None = None, iterations: int = 1, wait: float = 0.02) -> None:
    n = driver.num_leds
    for j in range(256 * max(1, iterations)):
        for i in range(n):
            pos = ((i * 256 // n) + j) & 255
            r, g, b = _wheel_tinted(pos, color)
            driver.set(i, r, g, b)
        driver.show()
        time.sleep(wait)


def spinner(driver: NeoDriver, color: Color, iterations: int = 1, wait: float = 0.1) -> None:
    n = driver.num_leds
    for _ in range(max(1, iterations)):
        for i in range(n):
            driver.clear()
            driver.set(i, *color)
            driver.show()
            time.sleep(wait)


def breathe(driver: NeoDriver, color: Color, iterations: int = 1, step: int = 5, wait: float = 0.02) -> None:
    r, g, b = color
    for _ in range(max(1, iterations)):
        for bright in range(0, 256, max(1, step)):
            rr = (r * bright) // 255
            gg = (g * bright) // 255
            bb = (b * bright) // 255
            driver.fill(rr, gg, bb)
            time.sleep(wait)
        for bright in range(255, -1, -max(1, step)):
            rr = (r * bright) // 255
            gg = (g * bright) // 255
            bb = (b * bright) // 255
            driver.fill(rr, gg, bb)
            time.sleep(wait)


def meteor_rain(driver: NeoDriver, color: Color, size: int = 5, decay_ms: int = 50) -> None:
    r, g, b = color
    n = driver.num_leds
    for i in range(n + size):
        driver.clear()
        for j in range(size):
            idx = i - j
            if 0 <= idx < n:
                driver.set(idx, r // (j + 1), g // (j + 1), b // (j + 1))
        driver.show()
        time.sleep(max(0.0, decay_ms / 1000.0))


def fire_flicker(driver: NeoDriver, color: Color, cycles: int = 1) -> None:
    r, g, b = color
    n = driver.num_leds
    for _ in range(max(1, cycles)):
        for i in range(n):
            flicker = random.randint(50, 255) / 255.0
            driver.set(i, _clamp(r * flicker), _clamp(g * flicker), _clamp(b * flicker))
        driver.show()
        time.sleep(random.uniform(0.05, 0.15))


def comet(driver: NeoDriver, color: Color, speed_ms: int = 50) -> None:
    r, g, b = color
    n = driver.num_leds
    for i in range(n):
        driver.clear()
        driver.set(i, r, g, b)
        if i > 0:
            driver.set(i - 1, r // 2, g // 2, b // 2)
        driver.show()
        time.sleep(max(0.0, speed_ms / 1000.0))


def wave(driver: NeoDriver, color: Color | None = None, wait: float = 0.05) -> None:
    n = driver.num_leds
    for j in range(0, 256, 5):
        for i in range(n):
            r, g, b = _wheel_tinted((i * 256 // n + j) & 255, color)
            driver.set(i, r, g, b)
        driver.show()
        time.sleep(wait)


def pulse(driver: NeoDriver, color: Color, step: int = 10, wait: float = 0.05) -> None:
    r, g, b = color
    for bright in range(0, 255, max(1, step)):
        ratio = bright / 255.0
        driver.fill(_clamp(r * ratio), _clamp(g * ratio), _clamp(b * ratio))
        time.sleep(wait)


def twinkle(driver: NeoDriver, color: Color, count: int = 5, wait: float = 0.1) -> None:
    n = driver.num_leds
    for _ in range(count):
        idx = random.randrange(n)
        driver.set(idx, *color)
        driver.show()
        time.sleep(wait)
        driver.set(idx, 0, 0, 0)
        driver.show()


def color_wipe(driver: NeoDriver, color: Color, speed_ms: int = 50) -> None:
    n = driver.num_leds
    for i in range(n):
        driver.set(i, *color)
        driver.show()
        time.sleep(max(0.0, speed_ms / 1000.0))


def random_blink(driver: NeoDriver, color: Color | None = None, wait: float = 0.1) -> None:
    n = driver.num_leds
    if color is None:
        for i in range(n):
            driver.set(i, random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    else:
        r, g, b = color
        for i in range(n):
            variation = random.randint(-30, 30)
            driver.set(i, _clamp(r + variation), _clamp(g + variation), _clamp(b + variation))
    driver.show()
    time.sleep(wait)


def theater_chase(driver: NeoDriver, color: Color, wait: float = 0.05, cycles: int = 5) -> None:
    n = driver.num_leds
    for _ in range(cycles):
        for q in range(3):
            for i in range(0, n, 3):
                if i + q < n:
                    driver.set(i + q, *color)
            driver.show()
            time.sleep(wait)
            for i in range(0, n, 3):
                if i + q < n:
                    driver.set(i + q, 0, 0, 0)


def snow(driver: NeoDriver, color: Color, flakes: int = 10, wait: float = 0.2) -> None:
    driver.clear()
    r, g, b = color
    n = driver.num_leds
    for _ in range(flakes):
        idx = random.randrange(n)
        intensity = random.randint(100, 255) / 255.0
        driver.set(idx, _clamp(r * intensity), _clamp(g * intensity), _clamp(b * intensity))
    driver.show()
    time.sleep(wait)


def alternating_colors(driver: NeoDriver, color1: Color, color2: Color, cycles: int = 10, wait: float = 0.1) -> None:
    n = driver.num_leds
    for j in range(cycles):
        for i in range(n):
            driver.set(i, *(color1 if (i + j) % 2 == 0 else color2))
        driver.show()
        time.sleep(wait)


def _lerp(a: int, b: int, t: float) -> int:
    return _clamp(a + (b - a) * t)


def _lerp_color(c1: Color, c2: Color, t: float) -> Color:
    return (_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t))


def multi_color_gradient(driver: NeoDriver, colors: Sequence[Color], iterations: int = 5, wait: float = 0.03) -> None:
    if not colors:
        return
    n = driver.num_leds
    k = len(colors)
    for _ in range(max(1, iterations)):
        for j in range(0, 256, 5):
            for i in range(n):
                segment = (i * k) // max(1, n)
                pos = (i * k * 256 // max(1, n)) % 256
                c1 = colors[segment % k]
                c2 = colors[(segment + 1) % k]
                t = pos / 255.0
                driver.set(i, *_lerp_color(c1, c2, t))
            driver.show()
            time.sleep(wait)


def multi_color_wave(driver: NeoDriver, colors: Sequence[Color], iterations: int = 5, wait: float = 0.03) -> None:
    if not colors:
        return
    n = driver.num_leds
    k = len(colors)
    for _ in range(max(1, iterations)):
        for j in range(0, 256, 5):
            for i in range(n):
                pos = (i * 256 // n + j) % 256
                segment = (pos * k) // 256
                seg_pos = (pos * k) % 256
                c1 = colors[segment % k]
                c2 = colors[(segment + 1) % k]
                t = seg_pos / 255.0
                driver.set(i, *_lerp_color(c1, c2, t))
            driver.show()
            time.sleep(wait)


def gradient_fade(driver: NeoDriver, cycles: int = 5, color: Color | None = None, wait: float = 0.03) -> None:
    n = driver.num_leds
    for j in range(cycles):
        for i in range(n):
            pos = int((i / max(1, n - 1)) * 255)
            driver.set(i, *_wheel_tinted((pos + j) % 256, color))
        driver.show()
        time.sleep(wait)


def bouncing_ball(driver: NeoDriver, color: Color, frames: int = 60, wait: float = 0.03) -> None:
    r, g, b = color
    n = driver.num_leds
    gravity = 0.1
    start_height = 1.0
    height = start_height
    velocity = 0.0
    dampening = 0.90
    for _ in range(frames):
        velocity += gravity
        height -= velocity
        if height < 0:
            height = 0
            velocity = -velocity * dampening
        pos = int((height * 100) / (start_height * 100) * (n - 1))
        driver.clear()
        if 0 <= pos < n:
            driver.set(pos, r, g, b)
        driver.show()
        time.sleep(wait)


def running_lights(driver: NeoDriver, color: Color, loops: int = 2, wait: float = 0.05) -> None:
    r, g, b = color
    n = driver.num_leds
    position = 0
    for _ in range(n * loops):
        position += 1
        for j in range(n):
            sin_val = math.sin((j + position) * 1.0) * 127 + 128
            ratio = sin_val / 255.0
            driver.set(j, _clamp(r * ratio), _clamp(g * ratio), _clamp(b * ratio))
        driver.show()
        time.sleep(wait)


def stacked_bars(driver: NeoDriver, wait_ms: int = 50, color: Color | None = None) -> None:
    n = driver.num_leds
    # Fill up
    for h in range(n):
        for i in range(h + 1):
            if color is None:
                driver.set(i, *base_wheel(int(i / max(1, n - 1) * 255)))
            else:
                driver.set(i, *color)
        driver.show()
        time.sleep(max(0.0, wait_ms / 1000.0))
    # Empty
    for h in range(n - 1, -1, -1):
        for i in range(h, n):
            driver.set(i, 0, 0, 0)
        driver.show()
        time.sleep(max(0.0, wait_ms / 1000.0))
