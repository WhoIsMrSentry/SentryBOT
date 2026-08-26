from __future__ import annotations

import sys
from typing import Any

from .console_types import ANSI_RE, LogEvent, Palette, ServiceStatus, TABS, UIState

ASCII_TRANSLATION = str.maketrans({
    "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
    "—": "-", "–": "-", "…": "...", "→": "->", "←": "<-",
    "•": "*", "·": "*", "✓": "OK", "✗": "X", "⚠": "!",
    "╭": "+", "╮": "+", "╰": "+", "╯": "+", "─": "-", "│": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "┬": "+", "┴": "+", "┼": "+", "═": "=", "║": "|",
    "█": "#", "░": ".", "▒": ".", "▓": "#", "›": ">", "‹": "<",
})


def repair_mojibake(text: str) -> str:
    if not text:
        return ""
    if "â" in text or "Ã" in text or "Â" in text:
        for enc in ("cp1252", "latin1"):
            try:
                fixed = text.encode(enc, errors="ignore").decode("utf-8", errors="ignore")
                if fixed and fixed != text and fixed.count("\ufffd") <= text.count("\ufffd"):
                    text = fixed
                    break
            except Exception:
                pass
    return text.replace("\ufffd", "?")


def safe_text(text: str) -> str:
    text = repair_mojibake(str(text)).translate(ASCII_TRANSLATION)
    return text.encode("ascii", errors="replace").decode("ascii")


def force_utf8_stdio() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def fit(text: str, width: int) -> str:
    text = safe_text(text).replace("\t", "    ").replace("\r", "")
    plain = strip_ansi(text)
    if len(plain) <= width:
        return text + " " * max(0, width - len(plain))
    if width <= 1:
        return "" if width <= 0 else "~"
    return plain[: max(0, width - 1)] + "~"


def crop(text: str, width: int) -> str:
    return fit(text, width)[:width]


def clean_path(path: str) -> str:
    path = safe_text(path).replace("\\", "/")
    marker = "Project SentryBOT V5/"
    if marker in path:
        return marker + path.split(marker, 1)[1]
    return path


def border_chars(ascii_mode: bool) -> tuple[str, str, str, str, str, str]:
    return ("+", "+", "+", "+", "-", "|")


def box(
    title: str,
    lines: list[str],
    width: int,
    height: int | None,
    pal: Palette,
    ascii_mode: bool = False,
) -> list[str]:
    tl, tr, bl, br, h, v = border_chars(ascii_mode)
    inner = max(2, width - 2)
    title_text = f" {title} "
    top = tl + title_text + h * max(0, inner - visible_len(title_text)) + tr
    out = [fit(top, width)]
    body_h = len(lines) if height is None else max(0, height - 2)
    for i in range(body_h):
        content = lines[i] if i < len(lines) else ""
        out.append(v + fit(content, inner) + v)
    bottom = bl + h * inner + br
    out.append(fit(bottom, width))
    return out[:height] if height else out


def hbar(value: int, maximum: int, width: int, pal: Palette) -> str:
    if maximum <= 0:
        maximum = 1
    filled = int(min(width, max(0, value) * width / maximum))
    bar = "#" * filled + "." * (width - filled)
    if value == 0:
        return pal.dim(bar)
    return pal.cyan(bar)


def service_card(svc: ServiceStatus, width: int, pal: Palette) -> list[str]:
    state = pal.level(svc.state)
    return [
        f"{svc.name:<7} {state}",
        pal.dim(f"{svc.last_seen:<8}") + " " + crop(svc.detail, max(8, width - 10)),
    ]


def event_line(ev: LogEvent, width: int, pal: Palette, compact: bool = False) -> str:
    lvl = ev.level.upper().replace("WARNING", "WARN")
    chan = ev.channel[:7].upper()
    src = ev.source[:18]
    msg = clean_path(ev.message)
    if compact:
        return fit(f"{pal.dim(ev.time)} {chan:<7} {pal.level(lvl):<9} {msg}", width)
    return fit(f"{pal.dim(ev.time)} {pal.level(lvl):<9} {chan:<7} {src:<18} {msg}", width)


def tab_strip(width: int, ui: UIState, pal: Palette) -> str:
    parts: list[str] = []
    for i, tab in enumerate(TABS):
        label = f"{i+1}:{tab}"
        parts.append(pal.cyan(label) if i == ui.active_tab else pal.dim(label))
    return fit("  ".join(parts), width)


def dict_get(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def yes_no(value: Any, pal: Palette, yes: str = "yes", no: str = "no") -> str:
    return pal.green(yes) if bool(value) else pal.yellow(no)


def render_kv(lines: list[str], key: str, value: Any, width: int, pal: Palette | None = None) -> None:
    val = safe_text("-" if value is None else str(value))
    key = safe_text(key)
    lines.append(f" {key:<22} {crop(val, max(8, width - 25))}")


def command_prompt(ui: UIState) -> str:
    if ui.command_mode == "filter":
        return "/" + ui.command_buffer
    if ui.command_mode == "project_search":
        return "search> " + ui.command_buffer
    if ui.command_mode == "command":
        return ":" + ui.command_buffer
    if ui.command_mode == "edit_key":
        return "edit key> " + ui.command_buffer
    if ui.command_mode == "edit_value":
        return f"{ui.pending_key}= " + ui.command_buffer
    return ui.message or "1-9 tabs  / filter  v view  s search  e edit config  : command  q quit"
