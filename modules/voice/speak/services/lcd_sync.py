"""Synchronized 20x4 Arduino LCD caption pager driven by live TTS playback."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from modules.arduino_serial.contract import build_lcd_cmd

logger = logging.getLogger("speak.lcd_sync")
_ORIG_REQUESTS_POST = requests.post if requests is not None else None

_TR_ASCII_MAP = str.maketrans(
    {
        "ç": "c",
        "Ç": "C",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "Ö": "O",
        "ş": "s",
        "Ş": "S",
        "ü": "u",
        "Ü": "U",
        "–": "-",
        "—": "-",
        "…": "...",
        "‘": "'",
        "’": "'",
        "“": "'",
        "”": "'",
        '"': "'",
        "\\": "/",
    }
)


def sanitize_lcd_text(text: str) -> str:
    """Normalize speech text to HD44780-safe printable ASCII without unescaped quotes."""
    raw = str(text or "").translate(_TR_ASCII_MAP)
    ascii_chars = [ch if 32 <= ord(ch) <= 126 else " " for ch in raw]
    return re.sub(r"\s+", " ", "".join(ascii_chars)).strip()


def _wrap_line_tokens(text: str, cols: int) -> List[str]:
    if not text:
        return []
    width = max(8, int(cols))
    lines: List[str] = []
    current = ""
    for word in text.split(" "):
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paginate_lcd_text(
    text: str,
    *,
    cols: int = 20,
    rows: int = 4,
    header: str = "",
) -> List[Tuple[str, ...]]:
    """Split text into 4-line pages bounded to `cols` ASCII characters per row."""
    cleaned = sanitize_lcd_text(text)
    if not cleaned:
        return []
    cols = max(8, min(20, int(cols)))
    rows = max(2, min(4, int(rows)))
    clean_header = sanitize_lcd_text(header)[:cols]
    body_rows = rows - 1 if clean_header and rows > 1 else rows

    wrapped = _wrap_line_tokens(cleaned, cols)
    if not wrapped:
        return []

    pages: List[Tuple[str, ...]] = []
    for idx in range(0, len(wrapped), body_rows):
        chunk_lines = wrapped[idx : idx + body_rows]
        page_rows: List[str] = [clean_header] if clean_header and rows > 1 else []
        page_rows.extend(chunk_lines)
        while len(page_rows) < 4:
            page_rows.append("")
        pages.append(tuple(line[:cols] for line in page_rows[:4]))
    return pages


def _compute_page_durations(
    pages: List[Tuple[str, ...]],
    total_duration_s: float,
    *,
    has_header: bool,
    min_page_sec: float,
) -> List[float]:
    if not pages:
        return []
    if len(pages) == 1:
        return [max(0.0, float(total_duration_s))]

    weights: List[int] = []
    body_start = 1 if has_header else 0
    for page in pages:
        body_chars = sum(len(line.strip()) for line in page[body_start:])
        weights.append(max(1, body_chars))

    total_dur = max(float(total_duration_s), len(pages) * max(0.25, float(min_page_sec)) * 0.5)
    weight_sum = float(sum(weights))
    durations = [total_dur * (w / weight_sum) for w in weights]
    return durations


class SpeechLcdSync:
    """Streams word-wrapped 20x4 speech captions to Arduino during TTS audio playback."""

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        *,
        full_cfg: Optional[Dict[str, Any]] = None,
        send_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> None:
        raw = dict(cfg or {})
        self.enabled = bool(raw.get("enabled", True))
        self.cols = max(8, min(20, int(raw.get("cols", 20))))
        self.rows = max(2, min(4, int(raw.get("rows", 4))))
        self.overlay = bool(raw.get("overlay", True))
        self.restore_on_finish = bool(raw.get("restore_on_finish", True))
        self.restore_delay_s = max(0.0, float(raw.get("restore_delay_s", 0.35)))
        self.min_page_sec = max(0.2, float(raw.get("min_page_sec", 0.75)))
        self.timeout_s = max(0.05, float(raw.get("timeout_s", 0.25)))
        self.fail_cooldown_s = max(0.0, float(raw.get("fail_cooldown_s", 10.0)))
        self.header = str(raw.get("header") or "")
        self.arduino_path = "/" + str(raw.get("arduino_path") or "/arduino/send").lstrip("/")
        self._base_cfg = full_cfg if isinstance(full_cfg, dict) else raw
        self._raw_gateway_url = str(raw.get("gateway_base_url") or "@gateway").strip()
        self._send_fn = send_fn

        self._lock = threading.RLock()
        self._generation = 0
        self._stop_event: Optional[threading.Event] = None
        self._pager_thread: Optional[threading.Thread] = None
        self._restore_timer: Optional[threading.Timer] = None
        self._session: Any = None
        self._cooldown_until = 0.0

    def _resolve_send_url(self) -> str:
        raw_base = self._raw_gateway_url.rstrip("/")
        if not raw_base or raw_base.startswith("@gateway"):
            try:
                from modules.gateway.url import gateway_url, resolve_gateway_base_url

                gw = resolve_gateway_base_url(self._base_cfg)
                suffix = raw_base[len("@gateway") :].lstrip("/") if raw_base.startswith("@gateway") else ""
                path = f"/{suffix}/{self.arduino_path.lstrip('/')}" if suffix else self.arduino_path
                return gateway_url(gw, path)
            except Exception:
                return f"http://127.0.0.1:8080{self.arduino_path}"
        return f"{raw_base}{self.arduino_path}"

    def _dispatch_payload(self, payload: Dict[str, Any]) -> bool:
        if self._send_fn is not None:
            try:
                return bool(self._send_fn(payload))
            except Exception as exc:
                logger.debug("speech lcd send_fn failed: %s", exc)
                return False

        if requests is None:
            return False
        now = time.monotonic()
        with self._lock:
            if now < self._cooldown_until:
                return False
        url = self._resolve_send_url()
        try:
            post_fn = getattr(requests, "post", None)
            if post_fn is _ORIG_REQUESTS_POST:
                with self._lock:
                    if self._session is None:
                        self._session = requests.Session()
                    sess = self._session
                resp = sess.post(url, json=payload, timeout=self.timeout_s)
            else:
                resp = requests.post(url, json=payload, timeout=self.timeout_s)
            ok = int(getattr(resp, "status_code", 0) or 0) < 500
            if not ok and self.fail_cooldown_s > 0:
                with self._lock:
                    self._cooldown_until = time.monotonic() + self.fail_cooldown_s
            return ok
        except Exception as exc:
            logger.debug("speech lcd dispatch failed: %s", exc)
            if self.fail_cooldown_s > 0:
                with self._lock:
                    self._cooldown_until = time.monotonic() + self.fail_cooldown_s
            return False

    def _cancel_restore_locked(self) -> None:
        timer = self._restore_timer
        self._restore_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _send_restore(self, expected_gen: int) -> None:
        with self._lock:
            if not self.enabled or expected_gen != self._generation:
                return
            self._restore_timer = None
        payload = build_lcd_cmd(overlay=self.overlay, restore=True)
        self._dispatch_payload(payload)

    def _run_pages(
        self,
        gen: int,
        pages: List[Tuple[str, ...]],
        durations: List[float],
        stop_event: threading.Event,
    ) -> None:
        for idx, page in enumerate(pages):
            if stop_event.is_set():
                return
            with self._lock:
                if gen != self._generation:
                    return
            payload = build_lcd_cmd(
                l1=page[0],
                l2=page[1],
                l3=page[2],
                l4=page[3],
                overlay=self.overlay,
            )
            self._dispatch_payload(payload)
            if idx < len(pages) - 1:
                wait_s = max(0.05, float(durations[idx]))
                if stop_event.wait(timeout=wait_s):
                    return

    def begin_utterance(self, text: str, duration_sec: float) -> Optional[int]:
        """Start synchronized 20x4 LCD paging for the active utterance."""
        if not self.enabled:
            return None
        pages = paginate_lcd_text(text, cols=self.cols, rows=self.rows, header=self.header)
        if not pages:
            return None
        durations = _compute_page_durations(
            pages,
            float(duration_sec or 0.0),
            has_header=bool(sanitize_lcd_text(self.header) and self.rows > 1),
            min_page_sec=self.min_page_sec,
        )
        with self._lock:
            self._cancel_restore_locked()
            if self._stop_event is not None:
                self._stop_event.set()
            self._generation += 1
            gen = self._generation
            stop_ev = threading.Event()
            self._stop_event = stop_ev
            thread = threading.Thread(
                target=self._run_pages,
                args=(gen, pages, durations, stop_ev),
                daemon=True,
                name="speak-lcd-sync",
            )
            self._pager_thread = thread
        thread.start()
        return gen

    def end_utterance(self, token: Optional[int] = None, *, interrupted: bool = False) -> None:
        """Stop paging and restore robot's idle Home screen (debounced unless interrupted)."""
        if not self.enabled:
            return
        with self._lock:
            if token is not None and token != self._generation:
                return
            if self._stop_event is not None:
                self._stop_event.set()
            gen = self._generation
            self._cancel_restore_locked()
            if not self.restore_on_finish:
                return
            if interrupted or self.restore_delay_s <= 0.0:
                threading.Thread(
                    target=self._send_restore,
                    args=(gen,),
                    daemon=True,
                    name="speak-lcd-restore",
                ).start()
                return
            timer = threading.Timer(self.restore_delay_s, self._send_restore, args=(gen,))
            timer.daemon = True
            self._restore_timer = timer
            timer.start()

    def close(self) -> None:
        with self._lock:
            self._generation += 1
            self._cancel_restore_locked()
            if self._stop_event is not None:
                self._stop_event.set()
            sess, self._session = self._session, None
        if sess is not None:
            try:
                sess.close()
            except Exception:
                pass


__all__ = ["SpeechLcdSync", "paginate_lcd_text", "sanitize_lcd_text"]
