from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from typing import Iterable

from .event_bus import RuntimeEvent

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class Border:
    top_left: str = "┌"
    top_right: str = "┐"
    bottom_left: str = "└"
    bottom_right: str = "┘"
    horizontal: str = "─"
    vertical: str = "│"
    tee_left: str = "├"
    tee_right: str = "┤"


ASCII_BORDER = Border("+", "+", "+", "+", "-", "|", "+", "+")
UNICODE_BORDER = Border()


class ConsoleRenderer:
    def __init__(self, *, colors: bool = True, max_width: int = 92, border: str = "rounded") -> None:
        self.colors = colors and self._stream_supports_color()
        self.max_width = max(54, int(max_width or 92))
        self.border = UNICODE_BORDER if border != "ascii" and self._stream_supports_unicode() else ASCII_BORDER

    def _stream_supports_color(self) -> bool:
        if os.getenv("NO_COLOR"):
            return False
        return bool(getattr(sys.stdout, "isatty", lambda: False)())

    def _stream_supports_unicode(self) -> bool:
        encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
        if "utf" in encoding:
            return True
        return os.name != "nt"

    def terminal_width(self) -> int:
        width = shutil.get_terminal_size((self.max_width, 24)).columns
        return max(54, min(self.max_width, width))

    def strip_ansi(self, value: str) -> str:
        return _ANSI_RE.sub("", value)

    def color(self, value: str, code: str) -> str:
        if not self.colors:
            return value
        return f"\x1b[{code}m{value}\x1b[0m"

    def chip(self, text: str, status: str = "INFO") -> str:
        status = status.upper()
        table = {
            "OK": "32",
            "READY": "32",
            "INFO": "36",
            "IDLE": "36",
            "WARN": "33",
            "WARNING": "33",
            "ERROR": "31",
            "FAIL": "31",
            "DEGRADED": "33",
        }
        return self.color(f"[{text:<5}]", table.get(status, "37"))

    def line(self, title: str = "") -> str:
        width = self.terminal_width()
        if not title:
            return self.border.horizontal * width
        text = f" {title.strip()} "
        pad = max(0, width - len(self.strip_ansi(text)))
        left = pad // 2
        right = pad - left
        return (self.border.horizontal * left) + text + (self.border.horizontal * right)

    def box(self, title: str, body_lines: Iterable[str]) -> str:
        width = self.terminal_width()
        inner = width - 2
        title_line = self.line(title)[1:-1] if width > 4 else title
        lines = [f"{self.border.top_left}{title_line}{self.border.top_right}"]
        for raw in body_lines:
            visible = self.strip_ansi(raw)
            if not raw:
                lines.append(f"{self.border.vertical}{' ' * inner}{self.border.vertical}")
                continue
            chunks = textwrap.wrap(visible, inner, replace_whitespace=False) or [""]
            if raw != visible and len(chunks) == 1:
                pad = inner - len(visible)
                lines.append(f"{self.border.vertical}{raw}{' ' * max(0, pad)}{self.border.vertical}")
            else:
                for chunk in chunks:
                    lines.append(f"{self.border.vertical}{chunk}{' ' * (inner - len(chunk))}{self.border.vertical}")
        lines.append(f"{self.border.bottom_left}{self.border.horizontal * inner}{self.border.bottom_right}")
        return "\n".join(lines)

    def progress(self, ratio: float, width: int = 12) -> str:
        ratio = max(0.0, min(1.0, float(ratio)))
        filled = int(round(width * ratio))
        return "█" * filled + "░" * (width - filled)

    def event_line(self, event: RuntimeEvent) -> str:
        created = time_label(event.created_at)
        tag = f"{event.channel:<7}"[:7]
        level = self.chip(event.status if event.status else event.level, event.status or event.level)
        msg = event.message.replace("\n", " ").strip()
        if event.duration_ms is not None:
            msg = f"{msg} | {event.duration_ms} ms"
        if event.trace_id:
            msg = f"trace={event.trace_id} | {msg}"
        return f"{created}  {tag} {level} {msg}"


def time_label(ts: float) -> str:
    import time

    return time.strftime("%H:%M:%S", time.localtime(ts))
