from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

logger = logging.getLogger("oled_faces.driver")


class PiSsd1306Driver:
    """SSD1306 I2C driver for Raspberry Pi; accepts PIL frames from the eye engine."""

    def __init__(self, cfg: Optional[Dict[str, object]] = None):
        c = dict(cfg or {})
        self.enabled = bool(c.get("enabled", True))
        self.bus_id = int(c.get("bus", 1))
        self.addr = int(c.get("address", 0x3C))
        self.width = int(c.get("width", 128))
        self.height = int(c.get("height", 64))
        self.contrast = max(0, min(255, int(c.get("contrast", 0x8F))))
        self._target_contrast = self.contrast
        self.dim_contrast = max(0, min(255, int(c.get("dim_contrast", 16))))
        self.burn_in_dim_s = max(0.0, float(c.get("burn_in_dim_s", 180.0)))
        self.burn_in_sleep_s = max(0.0, float(c.get("burn_in_sleep_s", 600.0)))
        self.column_offset = int(c.get("column_offset", 0))
        self.seg_remap = bool(c.get("seg_remap", True))
        self.com_scan_dec = bool(c.get("com_scan_dec", True))

        self._bus = None
        buf_len = (self.width * self.height) // 8
        self._buffer = bytearray(buf_len)
        self._prev_buffer: Optional[bytearray] = None
        self._ok = False
        self._begun = False
        self._closed_explicitly = False
        self._last_error = ""
        self._i2c_errors = 0
        self._consecutive_errors = 0
        self._reconnect_count = 0
        self._next_reconnect_ts = 0.0
        self._dimmed = False
        self._sleeping = False
        self._dirty_pages_last = 0
        self._last_activity_ts = time.monotonic()
        self._lock = threading.RLock()

    def begin(self) -> bool:
        with self._lock:
            self._closed_explicitly = False
            self._begun = True
            if not self.enabled:
                self._ok = False
                self._last_error = "display_disabled"
                return False
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        self._close_bus_locked()
        try:
            import smbus2  # type: ignore

            self._bus = smbus2.SMBus(self.bus_id)
            self._prev_buffer = None
            self._dimmed = False
            self._sleeping = False
            self._init_panel()
            self.clear()
            self.flush(force=True)
            self._ok = True
            self._last_error = ""
            self._consecutive_errors = 0
            self._next_reconnect_ts = 0.0
            self._last_activity_ts = time.monotonic()
            return True
        except Exception as exc:
            self._handle_i2c_error_locked(exc)
            return False

    def _close_bus_locked(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None

    def _handle_i2c_error_locked(self, exc: Exception) -> None:
        self._close_bus_locked()
        self._ok = False
        self._prev_buffer = None
        self._dimmed = False
        self._sleeping = False
        self._last_error = str(exc)
        self._i2c_errors += 1
        self._consecutive_errors += 1
        backoff = min(30.0, 0.5 * (2 ** min(5, self._consecutive_errors - 1)))
        self._next_reconnect_ts = time.monotonic() + backoff
        logger.debug("SSD1306 I2C error (retry in %.2fs): %s", backoff, exc)

    def _maybe_reconnect_locked(self) -> bool:
        if self._ok:
            return True
        if not self.enabled or not self._begun or self._closed_explicitly:
            return False
        if time.monotonic() < self._next_reconnect_ts:
            return False
        if self._connect_locked():
            self._reconnect_count += 1
            return True
        return False

    def close(self) -> None:
        with self._lock:
            self._closed_explicitly = True
            self._begun = False
            try:
                if self._bus is not None:
                    self.clear()
                    self.flush(force=True)
                    if not self._sleeping:
                        self._cmd(0xAE)
            except Exception:
                pass
            self._close_bus_locked()
            self._prev_buffer = None
            self._sleeping = False
            self._dimmed = False
            self._ok = False

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "ok": self._ok,
                "backend": "pi_ssd1306",
                "i2c_bus": self.bus_id,
                "i2c_addr": hex(self.addr),
                "size": [self.width, self.height],
                "contrast": self.contrast,
                "dimmed": self._dimmed,
                "sleeping": self._sleeping,
                "dirty_pages_last": self._dirty_pages_last,
                "i2c_errors": self._i2c_errors,
                "reconnect_count": self._reconnect_count,
                "column_offset": self.column_offset,
                "seg_remap": self.seg_remap,
                "com_scan_dec": self.com_scan_dec,
                "last_error": self._last_error,
            }

    def notify_activity(self) -> None:
        """Reset idle burn-in timer and wake display if dimmed/sleeping."""
        with self._lock:
            self._last_activity_ts = time.monotonic()
            if not self._ok or self._bus is None:
                return
            try:
                self._wake_panel_locked()
            except Exception as exc:
                self._handle_i2c_error_locked(exc)

    def wake(self) -> None:
        """Turn SSD1306 display back on (0xAF) and restore active contrast."""
        self.notify_activity()

    def sleep(self) -> None:
        """Put SSD1306 panel into low-power display-off mode (0xAE)."""
        with self._lock:
            if not self._ok or self._bus is None or self._sleeping:
                return
            try:
                self._cmd(0xAE)
                self._sleeping = True
            except Exception as exc:
                self._handle_i2c_error_locked(exc)

    def _wake_panel_locked(self) -> None:
        if self._sleeping:
            self._cmd(0xAF)
            self._sleeping = False
        if self._dimmed or self.contrast != self._target_contrast:
            self.contrast = self._target_contrast
            self._cmd(0x81)
            self._cmd(self._target_contrast)
            self._dimmed = False

    def show_pil_image(self, image: Any) -> None:
        with self._lock:
            if not self._ok and not self._maybe_reconnect_locked():
                return
            self._pil_to_buffer(image)
            dirty_pages = self._dirty_page_indices()
            now = time.monotonic()
            try:
                if dirty_pages:
                    self._last_activity_ts = now
                    self._wake_panel_locked()
                    self.flush(pages_to_write=dirty_pages)
                else:
                    self._dirty_pages_last = 0
                    self._apply_burn_in_guard_locked(now)
            except Exception as exc:
                self._handle_i2c_error_locked(exc)

    def _apply_burn_in_guard_locked(self, now: float) -> None:
        if self._bus is None:
            return
        idle_s = max(0.0, now - self._last_activity_ts)
        if self.burn_in_sleep_s > 0.0 and idle_s >= self.burn_in_sleep_s:
            if not self._sleeping:
                self._cmd(0xAE)
                self._sleeping = True
            return
        if self.burn_in_dim_s > 0.0 and idle_s >= self.burn_in_dim_s and not self._sleeping:
            if not self._dimmed and self.dim_contrast < self._target_contrast:
                self.contrast = self.dim_contrast
                self._cmd(0x81)
                self._cmd(self.dim_contrast)
                self._dimmed = True

    def show_test_pattern(self) -> bool:
        with self._lock:
            if not self._ok and not self._maybe_reconnect_locked():
                return False
            self.clear()
            for y in range(0, self.height, 8):
                for x in range(0, self.width, 8):
                    if ((x // 8) + (y // 8)) % 2 == 0:
                        self.fill_rect(x, y, 8, 8, 1)
            try:
                self._last_activity_ts = time.monotonic()
                self._wake_panel_locked()
                self.flush(force=True)
            except Exception as exc:
                self._handle_i2c_error_locked(exc)
                return False
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

    def _dirty_page_indices(self) -> List[int]:
        pages = self.height // 8
        if self._prev_buffer is None or len(self._prev_buffer) != len(self._buffer):
            return list(range(pages))
        dirty: List[int] = []
        w = self.width
        buf = self._buffer
        prev = self._prev_buffer
        for page in range(pages):
            start = page * w
            end = start + w
            if buf[start:end] != prev[start:end]:
                dirty.append(page)
        return dirty

    def flush(
        self,
        *,
        force: bool = False,
        pages_to_write: Optional[List[int]] = None,
    ) -> int:
        with self._lock:
            if self._bus is None:
                return 0
            pages = self.height // 8
            if force:
                targets = list(range(pages))
            elif pages_to_write is not None:
                targets = list(pages_to_write)
            else:
                targets = self._dirty_page_indices()
            col = max(0, min(127, int(self.column_offset)))
            col_lo = col & 0x0F
            col_hi = 0x10 | ((col >> 4) & 0x0F)
            for page in targets:
                self._cmd(0xB0 + page)
                self._cmd(col_lo)
                self._cmd(col_hi)
                start = page * self.width
                self._data(self._buffer[start:start + self.width])
            self._dirty_pages_last = len(targets)
            self._prev_buffer = bytearray(self._buffer)
            return len(targets)

    def set_brightness(self, value: int) -> None:
        """SSD1306 contrast 0..255; used by standby and mood-driven dimming."""
        with self._lock:
            level = max(0, min(255, int(value)))
            self._target_contrast = level
            if not self._ok and not self._maybe_reconnect_locked():
                self.contrast = level
                return
            if self._bus is None or self._sleeping:
                return
            if level == self.contrast and not self._dimmed:
                return
            self._dimmed = False
            self.contrast = level
            try:
                self._cmd(0x81)
                self._cmd(level)
            except Exception as exc:
                self._handle_i2c_error_locked(exc)

    def _pil_to_buffer(self, image: Any) -> None:
        img = image.convert("1")
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height))
        pages = self.height // 8
        if np is not None:
            bits = (np.asarray(img, dtype=np.uint8) != 0).reshape(pages, 8, self.width)
            packed = np.packbits(bits, axis=1, bitorder="little").reshape(-1)
            self._buffer[:] = packed.tobytes()
            return
        self.clear()
        px = img.load()
        for y in range(self.height):
            row_offset = (y // 8) * self.width
            bit = 1 << (y & 7)
            for x in range(self.width):
                if px[x, y]:
                    self._buffer[row_offset + x] |= bit

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
