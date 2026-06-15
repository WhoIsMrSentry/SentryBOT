from __future__ import annotations

import threading
from typing import Any, Dict, Optional


class PiSsd1306Driver:
    """SSD1306 I2C driver for Raspberry Pi; accepts PIL frames from the eye engine."""

    def __init__(self, cfg: Optional[Dict[str, object]] = None):
        c = dict(cfg or {})
        self.enabled = bool(c.get("enabled", True))
        self.bus_id = int(c.get("bus", 1))
        self.addr = int(c.get("address", 0x3C))
        self.width = int(c.get("width", 128))
        self.height = int(c.get("height", 64))
        self.contrast = int(c.get("contrast", 0x8F))
        self.column_offset = int(c.get("column_offset", 0))
        self.seg_remap = bool(c.get("seg_remap", True))
        self.com_scan_dec = bool(c.get("com_scan_dec", True))

        self._bus = None
        self._buffer = bytearray((self.width * self.height) // 8)
        self._ok = False
        self._last_error = ""
        self._lock = threading.Lock()

    def begin(self) -> bool:
        if not self.enabled:
            self._ok = False
            self._last_error = "display_disabled"
            return False
        try:
            import smbus2  # type: ignore

            self._bus = smbus2.SMBus(self.bus_id)
            self._init_panel()
            self.clear()
            self.flush()
            self._ok = True
            self._last_error = ""
            return True
        except Exception as exc:
            self._ok = False
            self._last_error = str(exc)
            return False

    def close(self) -> None:
        try:
            if self._bus is not None:
                self._bus.close()
        except Exception:
            pass
        self._bus = None
        self._ok = False

    def status(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "ok": self._ok,
            "backend": "pi_ssd1306",
            "i2c_bus": self.bus_id,
            "i2c_addr": hex(self.addr),
            "size": [self.width, self.height],
            "column_offset": self.column_offset,
            "seg_remap": self.seg_remap,
            "com_scan_dec": self.com_scan_dec,
            "last_error": self._last_error,
        }

    def show_pil_image(self, image: Any) -> None:
        if not self._ok:
            return
        with self._lock:
            self._pil_to_buffer(image)
            self.flush()

    def show_test_pattern(self) -> bool:
        if not self._ok:
            return False
        with self._lock:
            self.clear()
            for y in range(0, self.height, 8):
                for x in range(0, self.width, 8):
                    if ((x // 8) + (y // 8)) % 2 == 0:
                        self.fill_rect(x, y, 8, 8, 1)
            self.flush()
        return True

    def clear(self) -> None:
        for i in range(len(self._buffer)):
            self._buffer[i] = 0

    def set_pixel(self, x: int, y: int, on: int = 1) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        idx = x + (y // 8) * self.width
        bit = 1 << (y & 7)
        if on:
            self._buffer[idx] |= bit
        else:
            self._buffer[idx] &= ~bit

    def fill_rect(self, x: int, y: int, w: int, h: int, on: int = 1) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_pixel(xx, yy, on)

    def flush(self) -> None:
        if self._bus is None:
            return
        pages = self.height // 8
        col = max(0, min(127, int(self.column_offset)))
        for page in range(pages):
            self._cmd(0xB0 + page)
            self._cmd(col & 0x0F)
            self._cmd(0x10 | ((col >> 4) & 0x0F))
            start = page * self.width
            end = start + self.width
            self._data(self._buffer[start:end])

    def set_brightness(self, value: int) -> None:
        """SSD1306 contrast 0..255; used by standby and mood-driven dimming."""
        if not self._ok or self._bus is None:
            return
        level = max(0, min(255, int(value)))
        if level == self.contrast:
            return
        self.contrast = level
        self._cmd(0x81)
        self._cmd(level)

    def _pil_to_buffer(self, image: Any) -> None:
        img = image.convert("1")
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height))
        self.clear()
        px = img.load()
        for y in range(self.height):
            for x in range(self.width):
                if px[x, y]:
                    self.set_pixel(x, y, 1)

    def _cmd(self, c: int) -> None:
        if self._bus is None:
            return
        self._bus.write_byte_data(self.addr, 0x00, c & 0xFF)

    def _data(self, payload: bytes | bytearray) -> None:
        if self._bus is None:
            return
        i = 0
        n = len(payload)
        while i < n:
            chunk = list(payload[i:i + 16])
            self._bus.write_i2c_block_data(self.addr, 0x40, chunk)
            i += 16

    def _init_panel(self) -> None:
        seq = [
            0xAE, 0xD5, 0x80, 0xA8, self.height - 1, 0xD3, 0x00, 0x40,
            0x8D, 0x14, 0x20, 0x00,
            0xA1 if self.seg_remap else 0xA0,
            0xC8 if self.com_scan_dec else 0xC0,
            0xDA, 0x12 if self.height == 64 else 0x02,
            0x81, self.contrast, 0xD9, 0xF1, 0xDB, 0x40,
            0xA4, 0xA6, 0x2E, 0xAF,
        ]
        for c in seq:
            self._cmd(c)
