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
    """Backend that delegates LED driving to an attached Arduino via serial.

    This class keeps a local pixel buffer and sends the full pixel array
    to the Arduino when `update_strip` is called. The Arduino firmware is
    expected to accept a JSON/NDJSON command such as:
      { "cmd": "neopixel_pixels", "pixels": [[r,g,b], ...] }

    The implementation uses the high-level `ArduinoDriver` helper if
    available in the `modules.arduino_serial` module.
    """

    def __init__(self, device: str, num_leds: int) -> None:
        self.num_leds = num_leds
        self.buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * num_leds
        try:
            from modules.arduino_serial.services.driver import ArduinoDriver  # type: ignore
        except Exception:
            try:
                from ..arduino_serial.services.driver import ArduinoDriver  # type: ignore
            except Exception as exc:
                raise RuntimeError("Arduino support not available (modules.arduino_serial missing)") from exc

        # construct driver with possible port override via `device` string
        cfg_overrides = None
        if device and device.upper() != "AUTO":
            cfg_overrides = {"port": device}
        self._arduino = ArduinoDriver()
        try:
            self._arduino.start()
        except Exception:
            # best-effort; caller may start Arduino service separately
            pass

    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self.buf[idx] = (int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF)

    def clear_strip(self) -> None:
        self.buf = [(0, 0, 0)] * self.num_leds
        # notify Arduino immediately
        try:
            svc = getattr(self._arduino, "svc", None)
            if svc is None:
                # Arduino service not available; skip
                return
            svc.send({"cmd": "neopixel_clear"})
        except Exception:
            # best-effort; ignore
            pass

    def update_strip(self) -> None:
        # send full pixel buffer as list of [r,g,b]
        pix = [[r, g, b] for (r, g, b) in self.buf]
        try:
            svc = getattr(self._arduino, "svc", None)
            if svc is None:
                return
            svc.send({"cmd": "neopixel_pixels", "pixels": pix})
        except Exception:
            # best-effort: ignore if Arduino not reachable
            pass

    def animate(self, name: str, r: int, g: int, b: int, iterations: int, speed_ms: int) -> bool:
        try:
            svc = getattr(self._arduino, "svc", None)
            if svc is None:
                return False
            svc.send({
                "cmd": "neopixel_animate",
                "name": name,
                "r": r,
                "g": g,
                "b": b,
                "iterations": iterations,
                "speed_ms": speed_ms
            })
            return True
        except Exception:
            return False


class NeoDriver:
    def __init__(self, cfg: NeoDriverConfig) -> None:
        self.cfg = cfg
        self.num_leds = cfg.num_leds
        self.order = cfg.order.upper()

        self._strip: _StripProto
        backend = (cfg.backend or "auto").strip().lower()

        if backend in {"pi", "auto"}:
            try:
                from pi5neo import Pi5Neo  # type: ignore

                self._strip = Pi5Neo(cfg.device, num_leds=cfg.num_leds, spi_speed_khz=cfg.speed_khz)
                return
            except Exception:
                # fallthrough to Arduino or sim
                pass

        if backend in {"arduino"}:
            try:
                self._strip = _ArduinoStrip(cfg.device, num_leds=cfg.num_leds)
                return
            except Exception:
                pass

        # Fallback to simulator
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
        return self._strip.animate(name.lower(), r, g, b, iterations, speed_ms)

    # Helpers
    def _map_color(self, r: int, g: int, b: int) -> Tuple[int, int, int]:
        if self.order == "GRB":
            return (g, r, b)
        if self.order == "RGB":
            return (r, g, b)
        if self.order == "BRG":
            return (b, r, g)
        return (g, r, b)
