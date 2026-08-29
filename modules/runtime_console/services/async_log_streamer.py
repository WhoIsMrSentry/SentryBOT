from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Callable, NamedTuple
from rich.text import Text

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LOG_PARSE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?|\d{2}:\d{2}:\d{2})?\s*"
    r"(?:\[(?P<level>[A-Z]+)\]|(?P<level2>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL))\s*"
    r"(?:\[(?P<logger>[^\]]+)\])?\s*"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)

class ParsedLogEntry(NamedTuple):
    timestamp: str
    level: str
    logger: str
    message: str
    raw: str


def parse_log_line(raw_line: str) -> ParsedLogEntry:
    clean = ANSI_ESCAPE_RE.sub("", raw_line).strip()
    match = LOG_PARSE_RE.match(clean)
    if match:
        timestamp = match.group("time") or time.strftime("%H:%M:%S")
        level = (match.group("level") or match.group("level2") or "INFO").upper()
        if level == "WARNING":
            level = "WARN"
        logger = match.group("logger") or ""
        msg = match.group("message") or ""
        return ParsedLogEntry(timestamp=timestamp, level=level, logger=logger, message=msg, raw=clean)
    
    # Fallback if unformatted
    level = "INFO"
    upper = clean.upper()
    if "ERROR" in upper or "TRACEBACK" in upper or "EXCEPTION" in upper:
        level = "ERROR"
    elif "WARN" in upper:
        level = "WARN"
    elif "DEBUG" in upper:
        level = "DEBUG"

    return ParsedLogEntry(
        timestamp=time.strftime("%H:%M:%S"),
        level=level,
        logger="",
        message=clean,
        raw=clean,
    )


def format_log_entry_to_rich(entry: ParsedLogEntry) -> Text:
    text = Text()
    text.append(f"{entry.timestamp} ", style="dim")
    
    # Level styling
    if entry.level == "ERROR" or entry.level == "CRITICAL":
        text.append(f"[{entry.level:<5}] ", style="bold red")
    elif entry.level == "WARN":
        text.append(f"[{entry.level:<5}] ", style="bold yellow")
    elif entry.level == "DEBUG":
        text.append(f"[{entry.level:<5}] ", style="dim cyan")
    else:
        text.append(f"[{entry.level:<5}] ", style="bold green")
        
    if entry.logger:
        text.append(f"[{entry.logger}] ", style="cyan")
        
    # Message styling based on content
    msg_style = "white"
    if entry.level == "ERROR":
        msg_style = "bright_red"
    elif entry.level == "WARN":
        msg_style = "bright_yellow"
        
    text.append(entry.message, style=msg_style)
    return text


class AsyncLogStreamer:
    """Non-blocking background log reader for SentryBOT."""

    def __init__(self, root: Path, log_file: str = "logs/sentry.log") -> None:
        self.root = root
        self.log_path = root / log_file
        self.running = False
        self._last_pos = 0

    async def stream_logs(
        self,
        on_entry: Callable[[ParsedLogEntry, Text], None],
        max_initial_lines: int = 150,
    ) -> None:
        self.running = True
        
        # Initial read of existing tail
        if self.log_path.exists():
            try:
                size = self.log_path.stat().st_size
                read_size = min(size, 100_000)
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    if size > read_size:
                        f.seek(size - read_size)
                        f.readline()  # skip partial line
                    initial_lines = f.readlines()[-max_initial_lines:]
                    self._last_pos = f.tell()
                    
                for line in initial_lines:
                    if line.strip():
                        entry = parse_log_line(line)
                        rich_text = format_log_entry_to_rich(entry)
                        on_entry(entry, rich_text)
            except Exception:
                pass

        # Tail loop non-blocking
        while self.running:
            try:
                if self.log_path.exists():
                    current_size = self.log_path.stat().st_size
                    if current_size < self._last_pos:
                        # Log file rotated or truncated
                        self._last_pos = 0

                    if current_size > self._last_pos:
                        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self._last_pos)
                            new_lines = f.readlines()
                            self._last_pos = f.tell()

                        for line in new_lines:
                            if line.strip():
                                entry = parse_log_line(line)
                                rich_text = format_log_entry_to_rich(entry)
                                on_entry(entry, rich_text)
            except asyncio.CancelledError:
                self.running = False
                break
            except Exception:
                pass

            try:
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                self.running = False
                break

    def stop(self) -> None:
        self.running = False
