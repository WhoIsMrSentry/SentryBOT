from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

ASCII_ART_PATH = Path(__file__).resolve().parents[3] / "data" / "ascii-art.txt"


class Palette:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def c(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def reset(self, text: str) -> str:
        return text

    def bold(self, text: str) -> str:
        return self.c(text, "1")

    def dim(self, text: str) -> str:
        return self.c(text, "2")

    def red(self, text: str) -> str:
        return self.c(text, "31")

    def green(self, text: str) -> str:
        return self.c(text, "32")

    def yellow(self, text: str) -> str:
        return self.c(text, "33")

    def blue(self, text: str) -> str:
        return self.c(text, "34")

    def magenta(self, text: str) -> str:
        return self.c(text, "35")

    def cyan(self, text: str) -> str:
        return self.c(text, "36")

    def white(self, text: str) -> str:
        return self.c(text, "37")

    def gray(self, text: str) -> str:
        return self.c(text, "90")


def get_terminal_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24


def enable_virtual_terminal() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def scale_ascii_art(art: list[str], target_w: int, target_h: int) -> list[str]:
    from collections import Counter
    orig_h = len(art)
    if orig_h == 0:
        return art
    orig_w = len(art[0])
    if orig_w == 0 or (orig_h <= target_h and orig_w <= target_w):
        return art

    scaled = []
    for ty in range(target_h):
        sy1 = int(ty * orig_h / target_h)
        sy2 = max(sy1 + 1, int((ty + 1) * orig_h / target_h))
        row = []
        for tx in range(target_w):
            sx1 = int(tx * orig_w / target_w)
            sx2 = max(sx1 + 1, int((tx + 1) * orig_w / target_w))
            
            chars = []
            for y in range(sy1, min(sy2, orig_h)):
                for x in range(sx1, min(sx2, orig_w)):
                    c = art[y][x]
                    if c != ' ':
                        chars.append(c)
            
            if not chars:
                row.append(' ')
            else:
                row.append(Counter(chars).most_common(1)[0][0])
        scaled.append(''.join(row))
    return scaled


def load_ascii_art() -> list[str]:
    try:
        if ASCII_ART_PATH.exists():
            content = ASCII_ART_PATH.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()

            if not lines:
                return ["SENTRYBOT"]

            min_indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
            lines = [l[min_indent:].rstrip() for l in lines]

            max_w = max((len(l) for l in lines), default=0)
            lines = [l.ljust(max_w) for l in lines]
            
            term_w = shutil.get_terminal_size((80, 24)).columns
            allowed_w = max(30, term_w - 45)
            
            if max_w > allowed_w:
                ratio = max_w / len(lines)
                target_w = allowed_w
                target_h = int(target_w / ratio)
                lines = scale_ascii_art(lines, target_w, target_h)
                
            return lines
    except Exception:
        pass
    fallback = [
        "  SENTRYBOT  ",
        "  ▄▄▄▄▄▄▄▄▄▄▄▄  ",
        "  ████████████  ",
        "  ▀▀▀▀▀▀▀▀▀▀▀▀  ",
    ]
    max_w = max(len(l) for l in fallback)
    return [l.ljust(max_w) for l in fallback]


def get_ascii_art_width(art: list[str]) -> int:
    return max((len(line) for line in art), default=0)


def crop_ansi(text: str, width: int) -> str:
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    plain = ansi_re.sub("", text)
    if len(plain) <= width:
        return text
    result = ""
    visible = 0
    i = 0
    while i < len(text) and visible < width:
        if text[i] == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = text.find("m", i)
            if j != -1:
                result += text[i:j + 1]
                i = j + 1
                continue
        result += text[i]
        if text[i] != "\x1b":
            visible += 1
        i += 1
    return result + "\x1b[0m"
