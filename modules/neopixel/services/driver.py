from __future__ import annotations
from dataclasses import dataclass
import time
from typing import List, Tuple, Protocol


class _StripProto(Protocol):
    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None: ...
    def update_strip(self) -> None: ...
    def clear_strip(self) -> None: ...


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


@dataclass
class NeoDriverConfig:
    device: str = "/dev/spidev0.0"
    num_leds: int = 30
    speed_khz: int = 800
    order: str = "GRB"  # GRB | RGB | BRG

    # backend selection: auto | pi5neo | spi_ws2812 | sim
    backend: str = "auto"
    # For WS2812 over SPI (common on Jetson): typical is 2400kHz or 3200kHz.
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


class _SpiWs2812Strip:
    """WS2812/NeoPixel driver over SPI using 'spidev'.

    This is a pragmatic backend for boards like Jetson Nano where Pi-specific
    drivers (e.g. pi5neo) are unavailable.

    Encoding approach:
      - Use SPI at ~2.4MHz.
      - Map each WS2812 data bit to a 3-bit SPI symbol:
          0 -> 100
          1 -> 110
    """

    def __init__(self, device: str, num_leds: int, spi_khz: int = 2400) -> None:
        self.num_leds = num_leds
        self.buf: List[Tuple[int, int, int]] = [(0, 0, 0)] * num_leds

        try:
            import spidev  # type: ignore
        except Exception as exc:
            raise RuntimeError("spidev not available; install python package 'spidev'") from exc

        parsed = _parse_spidev_device(device)
        if not parsed:
            raise ValueError(f"Invalid SPI device path: {device}")
        bus, dev = parsed
        self._spi = spidev.SpiDev()
        self._spi.open(bus, dev)
        self._spi.mode = 0
        self._spi.max_speed_hz = int(spi_khz) * 1000

    def set_led_color(self, idx: int, r: int, g: int, b: int) -> None:
        if 0 <= idx < self.num_leds:
            self.buf[idx] = (int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF)

    def clear_strip(self) -> None:
        self.buf = [(0, 0, 0)] * self.num_leds

    def _encode_byte(self, value: int) -> List[int]:
        # Encode 8 WS2812 bits into 24 SPI bits, packed into 3 bytes.
        bits: List[int] = []
        for i in range(7, -1, -1):
            bit = (value >> i) & 1
            bits.extend([1, 1, 0] if bit else [1, 0, 0])
        out: List[int] = []
        cur = 0
        n = 0
        for b in bits:
            cur = (cur << 1) | b
            n += 1
            if n == 8:
                out.append(cur)
                cur = 0
                n = 0
        if n:
            out.append(cur << (8 - n))
        return out

    def update_strip(self) -> None:
        payload: List[int] = []
        for r, g, b in self.buf:
            payload.extend(self._encode_byte(r))
            payload.extend(self._encode_byte(g))
            payload.extend(self._encode_byte(b))

        # Reset/latch: send a low period (>50us). Zeros on SPI do that.
        payload.extend([0x00] * 64)

        # Write in chunks to avoid huge single write on some drivers.
        chunk = 4096
        for i in range(0, len(payload), chunk):
            self._spi.xfer2(payload[i : i + chunk])


class NeoDriver:
    def __init__(self, cfg: NeoDriverConfig) -> None:
        self.cfg = cfg
        self.num_leds = cfg.num_leds
        self.order = cfg.order.upper()

        self._strip: _StripProto
        backend = (cfg.backend or "auto").strip().lower()

        if backend in {"pi5neo", "auto"}:
            try:
                # Optional dependency; primarily for Raspberry Pi 5 SPI setup
                from pi5neo import Pi5Neo  # type: ignore

                self._strip = Pi5Neo(cfg.device, num_leds=cfg.num_leds, spi_speed_khz=cfg.speed_khz)
                return
            except Exception:
                pass

        if backend in {"spi", "spi_ws2812", "ws2812_spi", "auto"}:
            try:
                # Generic WS2812-over-SPI backend (Jetson-friendly)
                spi_khz = int(cfg.ws2812_spi_khz or 2400)
                self._strip = _SpiWs2812Strip(cfg.device, num_leds=cfg.num_leds, spi_khz=spi_khz)
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

    # Helpers
    def _map_color(self, r: int, g: int, b: int) -> Tuple[int, int, int]:
        if self.order == "GRB":
            return (g, r, b)
        if self.order == "RGB":
            return (r, g, b)
        if self.order == "BRG":
            return (b, r, g)
        return (g, r, b)
