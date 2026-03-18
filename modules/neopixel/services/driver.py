from __future__ import annotations
from dataclasses import dataclass
import time
from typing import List, Tuple, Protocol


class _StripProto(Protocol):
    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None: ...
    def update_strip(self) -> None: ...
    def clear_strip(self) -> None: ...
    def animate(self, name: str, r: int, g: int, b: int, iterations: int, speed_ms: int) -> bool: ...


class _SimStrip:
    """Simple simulator for development environments without hardware.

    Prints basic actions and keeps an in-memory buffer.
    """

    def __init__(self, num_leds: int) -> None:
        self.num_leds = num_leds
        self.buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * num_leds

    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self.buf[idx] = (r, g, b)

    def update_strip(self) -> None:
        # No-op; in real use we could log or visualize
        pass

    def clear_strip(self) -> None:
        self.buf = [(0, 0, 0)] * self.num_leds

    def animate(self, name: str, r: int, g: int, b: int, iterations: int, speed_ms: int) -> bool:
        # Simulator doesn't play hardware animations
        return False


@dataclass
class NeoDriverConfig:
    device: str = "/dev/spidev0.0"
    num_leds: int = 30
    speed_khz: int = 800
    order: str = "GRB"  # GRB | RGB | BRG

    # backend selection: auto | pi | arduino | sim
    # - `pi`     : Raspberry Pi native driver (pi5neo)
    # - `arduino`: Arduino attached over serial will drive the LEDs (preferred for this project)
    # - `sim`    : software simulator / no-op
    backend: str = "auto"
    # When using Arduino backend the `device` may be a serial port or 'AUTO'
    ws2812_spi_khz: int = 2400


def _parse_spidev_device(path: str) -> tuple[int, int] | None:
    # Expected format: /dev/spidev<bus>.<device>
    try:
        base = path.rsplit("/", 1)[-1]
        if not base.startswith("spidev"):
            return None
        rest = base[len("spidev") :]
        bus_s, dev_s = rest.split(".", 1)
        return int(bus_s), int(dev_s)
    except Exception:
        return None


class _ArduinoStrip:
    """
    Arduino backend support removed in favor of Pi native driver.
    This project now prefers the `pi5neo` backend; if unavailable a
    simulator `_SimStrip` is used. Previously the Arduino strip delegated
    animations via serial; that code has been removed to simplify the
    supported backends and ensure animations are attempted on the Pi-side.
    """


class NeoDriver:
    def __init__(self, cfg: NeoDriverConfig) -> None:
        self.cfg = cfg
        self.num_leds = cfg.num_leds
        self.order = cfg.order.upper()
        # Only Pi native backend is supported now; attempt to use `pi5neo`.
        try:
            from pi5neo import Pi5Neo  # type: ignore
            self._strip = Pi5Neo(cfg.device, num_leds=cfg.num_leds, spi_speed_khz=cfg.speed_khz)
        except Exception:
            # Fallback to simulator when pi5neo not available
            self._strip = _SimStrip(cfg.num_leds)

    # Basic primitives
    def clear(self) -> None:
        self._strip.clear_strip()
        self._strip.update_strip()

    def set(self, idx: int, r: int, g: int, b: int) -> None:
        rr, gg, bb = self._map_color(r, g, b)
        self._strip.set_led_color(idx, rr, gg, bb)

    def show(self) -> None:
        self._strip.update_strip()

    def fill(self, r: int, g: int, b: int) -> None:
        for i in range(self.num_leds):
            self.set(i, r, g, b)
        self.show()

    def animate(self, name: str, r: int = 255, g: int = 255, b: int = 255, iterations: int = 0, speed_ms: int = 50) -> bool:
        """Attempts to play a hardware-accelerated animation.
        Returns True if the backend handled it, False if we need to fall back to software.
        """
        # Some Pi5Neo versions don't expose `animate`; fall back to software
        # animations in runner instead of raising AttributeError.
        fn = getattr(self._strip, "animate", None)
        if callable(fn):
            try:
                return bool(fn(name.lower(), r, g, b, iterations, speed_ms))
            except Exception:
                return False
        return False

    # Helpers
    def _map_color(self, r: int, g: int, b: int) -> Tuple[int, int, int]:
        if self.order == "GRB":
            return (g, r, b)
        if self.order == "RGB":
            return (r, g, b)
        if self.order == "BRG":
            return (b, r, g)
        return (g, r, b)
