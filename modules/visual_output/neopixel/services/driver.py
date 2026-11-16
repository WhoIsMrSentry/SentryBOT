from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Protocol, Tuple

from modules.common.color_utils import clamp_rgb

logger = logging.getLogger("neopixel.driver")

NEOPIXEL_SAFE_DEGRADED_DRIVER_CONTRACT = True
NEOPIXEL_SIMULATOR_BACKEND_ROLE = "safe_degraded_memory_only_led_buffer"


class _StripProto(Protocol):
    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None: ...
    def update_strip(self) -> None: ...
    def clear_strip(self) -> None: ...
    def animate(self, name: str, r: int, g: int, b: int, iterations: int, speed_ms: int) -> bool: ...


class _SimStrip:
    """Simple simulator for development environments without hardware.

    Keeps an in-memory RGB buffer for inspection and tests.
    """

    def __init__(self, num_leds: int) -> None:
        self.num_leds = num_leds
        self.buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * num_leds

    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self.buf[idx] = (r, g, b)

    def update_strip(self) -> None:
        # Safe degraded simulator update; no physical LED hardware is touched.
        pass

    def clear_strip(self) -> None:
        self.buf = [(0, 0, 0)] * self.num_leds

    def animate(self, name: str, r: int, g: int, b: int, iterations: int, speed_ms: int) -> bool:
        return False


@dataclass
class NeoDriverConfig:
    device: str = "/dev/spidev0.0"
    num_leds: int = 30
    speed_khz: int = 800
    order: str = "GRB"  # GRB | RGB | BRG
    backend: str = "auto"  # auto | pi | sim
    ws2812_spi_khz: int = 2400
    max_brightness: float = 0.7
    max_current_ma: int = 900  # 0 disables current cap


class NeoDriver:
    """Hardware-safe WS2812 driver with SPI backend selection and power limiting."""

    _PER_CHANNEL_MA = 20.0

    def __init__(self, cfg: NeoDriverConfig) -> None:
        self.cfg = cfg
        self.num_leds = max(0, int(cfg.num_leds))
        self.order = str(cfg.order or "GRB").upper()
        self.max_brightness = max(0.0, min(1.0, float(getattr(cfg, "max_brightness", 0.7))))
        self.max_current_ma = max(0, int(getattr(cfg, "max_current_ma", 900)))
        self._rgb_buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * self.num_leds
        self._last_estimated_ma: float = 0.0
        self._last_scale_factor: float = self.max_brightness

        backend = str(getattr(cfg, "backend", "auto") or "auto").strip().lower()
        spi_khz = int(getattr(cfg, "ws2812_spi_khz", 0) or getattr(cfg, "speed_khz", 2400) or 2400)
        self.active_spi_khz = spi_khz

        if backend == "sim":
            self._strip: _StripProto = _SimStrip(self.num_leds)
            self.backend_used = "sim"
        elif backend == "arduino":
            logger.info("Arduino NeoPixel backend is deprecated on host driver; using simulator buffer")
            self._strip = _SimStrip(self.num_leds)
            self.backend_used = "sim"
        else:
            try:
                from pi5neo import Pi5Neo  # type: ignore

                self._strip = Pi5Neo(cfg.device, num_leds=self.num_leds, spi_speed_khz=spi_khz)
                self.backend_used = "pi"
            except Exception as exc:
                logger.warning(
                    "Pi5Neo SPI init failed (%s, device=%s, spi_khz=%s); falling back to simulator",
                    exc,
                    cfg.device,
                    spi_khz,
                )
                self._strip = _SimStrip(self.num_leds)
                self.backend_used = "sim"

        self._is_sim = isinstance(self._strip, _SimStrip)

    def _compute_scale_factor(self) -> float:
        b = self.max_brightness
        if b <= 0.0 or not self._rgb_buf:
            self._last_estimated_ma = 0.0
            self._last_scale_factor = 0.0
            return 0.0
        est_ma = sum((r + g + bl) for r, g, bl in self._rgb_buf) / 255.0 * self._PER_CHANNEL_MA * b
        scale = b
        if self.max_current_ma > 0 and est_ma > float(self.max_current_ma):
            scale = b * (float(self.max_current_ma) / est_ma)
            est_ma = float(self.max_current_ma)
        self._last_estimated_ma = round(est_ma, 2)
        self._last_scale_factor = round(scale, 4)
        return scale

    def _encode_pixel(self, r: int, g: int, b: int, scale: float) -> Tuple[int, int, int]:
        sr = max(0, min(255, int(round(r * scale))))
        sg = max(0, min(255, int(round(g * scale))))
        sb = max(0, min(255, int(round(b * scale))))
        return (sr, sg, sb) if self._is_sim else self._map_color(sr, sg, sb)

    def power_status(self) -> Dict[str, object]:
        return {
            "backend": self.backend_used,
            "spi_khz": self.active_spi_khz,
            "max_brightness": self.max_brightness,
            "max_current_ma": self.max_current_ma,
            "last_estimated_ma": self._last_estimated_ma,
            "last_scale_factor": self._last_scale_factor,
        }

    # Basic primitives
    def clear(self) -> None:
        self._rgb_buf = [(0, 0, 0)] * self.num_leds
        self._last_estimated_ma = 0.0
        self._last_scale_factor = self.max_brightness
        self._strip.clear_strip()
        self._strip.update_strip()

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            rgb = clamp_rgb(r, g, b)
            self._rgb_buf[idx] = rgb
            er, eg, eb = self._encode_pixel(*rgb, self.max_brightness)
            self._strip.set_led_color(idx, er, eg, eb)

    def show(self) -> None:
        scale = self._compute_scale_factor()
        if abs(scale - self.max_brightness) > 1e-6:
            for idx, rgb in enumerate(self._rgb_buf):
                er, eg, eb = self._encode_pixel(*rgb, scale)
                self._strip.set_led_color(idx, er, eg, eb)
        self._strip.update_strip()

    def fill(self, r: int, g: int, b: int) -> None:
        rgb = clamp_rgb(r, g, b)
        self._rgb_buf = [rgb] * self.num_leds
        scale = self._compute_scale_factor()
        er, eg, eb = self._encode_pixel(*rgb, scale)
        for i in range(self.num_leds):
            self._strip.set_led_color(i, er, eg, eb)
        self._strip.update_strip()

    def animate(
        self,
        name: str,
        r: int = 255,
        g: int = 255,
        b: int = 255,
        iterations: int = 0,
        speed_ms: int = 50,
    ) -> bool:
        """Attempt hardware-accelerated animation (with power & channel-order mapping)."""
        fn = getattr(self._strip, "animate", None)
        if not callable(fn):
            return False
        rgb = clamp_rgb(r, g, b)
        er, eg, eb = self._encode_pixel(*rgb, self.max_brightness)
        try:
            return bool(fn(name.lower(), er, eg, eb, iterations, speed_ms))
        except Exception:
            return False

    # Helpers
    def _map_color(self, r: int, g: int, b: int) -> Tuple[int, int, int]:
        if self.order == "RGB":
            return (r, g, b)
        if self.order == "BRG":
            return (b, r, g)
        return (g, r, b)
