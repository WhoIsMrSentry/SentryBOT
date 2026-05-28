from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PiSsd1306Driver:
    """SSD1306 I2C driver that renders Irisoled assets from disk on Raspberry Pi."""

    def __init__(self, cfg: Optional[Dict[str, object]] = None):
        c = dict(cfg or {})
        self.enabled = bool(c.get("enabled", True))
        self.bus_id = int(c.get("bus", 1))
        self.addr = int(c.get("address", 0x3C))
        self.width = int(c.get("width", 128))
        self.height = int(c.get("height", 64))
        self.contrast = int(c.get("contrast", 0x8F))
        # Irisoled C++ assets are intended for Adafruit drawBitmap (XBM-like
        # row-major bit packing). Convert to SSD1306 page layout on load.
        self.bitmap_format = str(c.get("bitmap_format", "irisoled_xbm")).strip().lower()
        self.bitmap_bit_order = str(c.get("bitmap_bit_order", "lsb")).strip().lower()
        self.bitmap_mirror_x = bool(c.get("bitmap_mirror_x", False))
        self.bitmap_mirror_y = bool(c.get("bitmap_mirror_y", False))
        self.bitmap_invert = bool(c.get("bitmap_invert", False))
        # Panel wiring/config tuning knobs.
        self.column_offset = int(c.get("column_offset", 0))
        self.seg_remap = bool(c.get("seg_remap", True))
        self.com_scan_dec = bool(c.get("com_scan_dec", True))

        default_assets = Path(__file__).resolve().parent.parent / "assets"
        self.assets_dir = Path(str(c.get("assets_dir", default_assets))).resolve()
        self.bitmaps_subdir = str(c.get("bitmaps_subdir", "bitmaps")).strip() or "bitmaps"
        self.bitmaps_dir = self.assets_dir / self.bitmaps_subdir
        self.animations_dir = self.assets_dir / "animations"

        self._bus = None
        self._buffer = bytearray((self.width * self.height) // 8)
        self._ok = False
        self._last_error = ""

        self._bitmap_cache: Dict[str, bytes] = {}
        self._anim_cache: Dict[str, Tuple[List[str], float]] = {}

        self._lock = threading.Lock()
        self._anim_thread: Optional[threading.Thread] = None
        self._anim_stop = threading.Event()

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
        self.stop_animation()
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
            "assets_dir": str(self.assets_dir),
            "bitmaps_subdir": self.bitmaps_subdir,
            "bitmap_format": self.bitmap_format,
            "bitmap_bit_order": self.bitmap_bit_order,
            "column_offset": self.column_offset,
            "seg_remap": self.seg_remap,
            "com_scan_dec": self.com_scan_dec,
            "last_error": self._last_error,
        }

    def show_logo(self) -> bool:
        return self.show_bitmap("logo")

    def show_bitmap(self, name: str) -> bool:
        if not self._ok:
            return False
        key = str(name or "normal").strip().lower()
        bmp = self._load_bitmap(key)
        if bmp is None and key != "normal":
            bmp = self._load_bitmap("normal")
        if bmp is None:
            # No committed bitmap asset: keep the eyes expressive by drawing a
            # procedural face for this expression directly into the buffer.
            return self._render_procedural_face(key)
        with self._lock:
            self._buffer[:] = bmp
            self.flush()
        return True

    def _render_procedural_face(self, name: str) -> bool:
        try:
            from .procedural_face import draw_face
        except Exception:
            from procedural_face import draw_face  # type: ignore
        with self._lock:
            self.clear()
            draw_face(name, self.width, self.height, lambda x, y: self.set_pixel(x, y, 1))
            self.flush()
        return True

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

    def start_animation(self, name: str) -> bool:
        if not self._ok:
            return False
        key = str(name or "").strip().lower()
        frames, delay = self._load_animation(key)
        if not frames:
            return False

        self.stop_animation()
        self._anim_stop.clear()

        def _run() -> None:
            idx = 0
            while not self._anim_stop.is_set():
                self.show_bitmap(frames[idx])
                idx = (idx + 1) % len(frames)
                self._anim_stop.wait(delay)

        self._anim_thread = threading.Thread(target=_run, name="pi-oled-anim", daemon=True)
        self._anim_thread.start()
        return True

    def stop_animation(self) -> None:
        self._anim_stop.set()
        if self._anim_thread and self._anim_thread.is_alive():
            self._anim_thread.join(timeout=0.4)
        self._anim_thread = None

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
        # Some panels/controllers are shifted by a few columns (common with
        # SH1106-like wiring). Keep configurable for image alignment tuning.
        col = max(0, min(127, int(self.column_offset)))
        for page in range(pages):
            self._cmd(0xB0 + page)
            self._cmd(col & 0x0F)
            self._cmd(0x10 | ((col >> 4) & 0x0F))
            start = page * self.width
            end = start + self.width
            self._data(self._buffer[start:end])

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
            0xAE,
            0xD5,
            0x80,
            0xA8,
            self.height - 1,
            0xD3,
            0x00,
            0x40,
            0x8D,
            0x14,
            0x20,
            0x00,
            0xA1 if self.seg_remap else 0xA0,
            0xC8 if self.com_scan_dec else 0xC0,
            0xDA,
            0x12 if self.height == 64 else 0x02,
            0x81,
            self.contrast,
            0xD9,
            0xF1,
            0xDB,
            0x40,
            0xA4,
            0xA6,
            0x2E,
            0xAF,
        ]
        for c in seq:
            self._cmd(c)

    def _load_bitmap(self, name: str) -> Optional[bytes]:
        key = str(name).strip().lower()
        cached = self._bitmap_cache.get(key)
        if cached is not None:
            return cached

        path = self.bitmaps_dir / f"{key}.bin"
        if not path.exists():
            return None

        try:
            raw = path.read_bytes()
            size = len(self._buffer)
            if len(raw) < size:
                raw = raw + (b"\x00" * (size - len(raw)))
            elif len(raw) > size:
                raw = raw[:size]
            out = raw
            if self.bitmap_format in {"irisoled_xbm", "xbm", "xbm_lsb"}:
                out = self._convert_xbm_to_page_buffer(raw)
            if self.bitmap_invert:
                out = bytes((~b) & 0xFF for b in out)
            self._bitmap_cache[key] = out
            return out
        except Exception:
            return None

    def _convert_xbm_to_page_buffer(self, raw: bytes) -> bytes:
        """Convert XBM-style row-major bitmap to SSD1306 page layout.

        Irisoled bitmaps are consumed by Adafruit `drawBitmap`, which expects
        horizontal bytes and LSB-first bit order per byte. SSD1306 GDDRAM,
        however, is page-oriented (8 vertical pixels per byte). This converter
        bridges that layout difference.
        """
        w = self.width
        h = self.height
        row_bytes = w // 8
        size = (w * h) // 8
        if len(raw) < size:
            raw = raw + (b"\x00" * (size - len(raw)))
        elif len(raw) > size:
            raw = raw[:size]

        out = bytearray(size)
        for y in range(h):
            sy = (h - 1 - y) if self.bitmap_mirror_y else y
            for x in range(w):
                sx = (w - 1 - x) if self.bitmap_mirror_x else x
                src_idx = sy * row_bytes + (sx // 8)
                if self.bitmap_bit_order == "msb":
                    src_bit = 1 << (7 - (sx & 7))
                else:
                    src_bit = 1 << (sx & 7)
                on = (raw[src_idx] & src_bit) != 0
                if on:
                    dst_idx = x + (y // 8) * w
                    out[dst_idx] |= 1 << (y & 7)
        return bytes(out)

    def _load_animation(self, name: str) -> Tuple[List[str], float]:
        key = str(name).strip().lower()
        cached = self._anim_cache.get(key)
        if cached is not None:
            return cached

        path = self.animations_dir / f"{key}.json"
        if not path.exists():
            return ([], 0.2)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            frames = [str(x).strip().lower() for x in data.get("frames", []) if str(x).strip()]
            delay_ms = int(data.get("delay_ms", 180))
            delay = max(0.05, float(delay_ms) / 1000.0)
            out = (frames, delay)
            self._anim_cache[key] = out
            return out
        except Exception:
            return ([], 0.2)
