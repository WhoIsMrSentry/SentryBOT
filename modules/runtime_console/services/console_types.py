from __future__ import annotations

import os
import re
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .console_constants import (
    RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT,
    RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE,
    APP,
    TITLE,
    VERSION,
    DEFAULT_REFRESH,
    MAX_TAIL_BYTES,
    MAX_SEARCH_FILE_BYTES,
    SEARCH_EXTS,
    ANSI_RE,
    LEVEL_ORDER,
    TABS,
    PC_EXPECTED_HINTS,
    SERVICE_RULES,
    CHANNEL_HINTS,
    NOISE_HINTS,
    BLOCKER_HINTS,
)


LOG_RE = re.compile(
    r"^(?P<time>\d\d:\d\d:\d\d)\s+\|\s+(?P<level>[A-Z]+)\s+\|\s+(?P<src>[^|]+?)\s*\|\s+(?P<msg>.*)$"
)
COMPACT_RE = re.compile(
    r"^(?P<time>\d\d:\d\d:\d\d)\s+(?P<chan>[A-Z_]+)\s+\[(?P<level>[^\]]+)\]\s+(?P<msg>.*)$"
)
HTTP_RE = re.compile(r'"(?P<method>GET|POST|PUT|PATCH|DELETE)\s+(?P<path>/[^\s?\"]+)')
REMOTE_RE = re.compile(
    r"\b(?P<host>127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|localhost):(?P<port>\d+)\b"
)


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def c(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def dim(self, text: str) -> str:
        return self.c(text, "2")

    def bold(self, text: str) -> str:
        return self.c(text, "1")

    def cyan(self, text: str) -> str:
        return self.c(text, "36")

    def blue(self, text: str) -> str:
        return self.c(text, "34")

    def green(self, text: str) -> str:
        return self.c(text, "32")

    def yellow(self, text: str) -> str:
        return self.c(text, "33")

    def red(self, text: str) -> str:
        return self.c(text, "31")

    def magenta(self, text: str) -> str:
        return self.c(text, "35")

    def level(self, level: str) -> str:
        u = level.upper().strip()
        if u in {"ERR", "ERROR", "CRITICAL"}:
            return self.red(u)
        if u in {"WARN", "WARNING"}:
            return self.yellow("WARN")
        if u in {"OK", "READY"}:
            return self.green(u)
        if u == "DEBUG":
            return self.dim(u)
        if u == "IDLE":
            return self.blue(u)
        return self.cyan(u)


@dataclass
class LogEvent:
    time: str
    level: str
    source: str
    channel: str
    message: str
    raw: str
    _search_blob: str = ""
    _is_debug: bool = False
    _is_warn_or_err: bool = False

    def __post_init__(self) -> None:
        lvl = self.level.upper().replace("WARNING", "WARN")
        self._is_debug = (lvl == "DEBUG")
        self._is_warn_or_err = (lvl in {"WARN", "ERROR", "CRITICAL"})
        if not self._search_blob:
            self._search_blob = f"{self.raw} {self.message} {self.source} {self.channel}".lower()


@dataclass
class ServiceStatus:
    name: str
    state: str = "IDLE"
    detail: str = "waiting"
    last_seen: str = "--:--:--"


@dataclass
class SearchResult:
    path: str
    line: int
    text: str


@dataclass
class Snapshot:
    services: dict[str, ServiceStatus] = field(
        default_factory=lambda: {
            k: ServiceStatus(k) for k in ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE", "CONFIG"]
        }
    )
    events: deque[LogEvent] = field(default_factory=lambda: deque(maxlen=2500))
    raw_lines: deque[str] = field(default_factory=lambda: deque(maxlen=5000))
    counts: Counter[str] = field(default_factory=Counter)
    endpoints: Counter[str] = field(default_factory=Counter)
    blockers: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    remote_hosts: Counter[str] = field(default_factory=Counter)
    camera_status: dict[str, Any] = field(default_factory=dict)
    camera_onsensor: dict[str, Any] = field(default_factory=dict)
    camera_probe_error: str = ""
    camera_probe_url: str = ""
    camera_last_probe: float = 0.0
    expression_state: dict[str, Any] = field(default_factory=dict)
    expression_status: dict[str, Any] = field(default_factory=dict)
    expression_history: dict[str, Any] = field(default_factory=dict)
    expression_probe_error: str = ""
    expression_probe_url: str = ""
    expression_last_probe: float = 0.0
    expression_output_status: dict[str, Any] = field(default_factory=dict)
    expression_output_plan: dict[str, Any] = field(default_factory=dict)
    expression_output_probe_error: str = ""
    expression_output_last_probe: float = 0.0
    companion_needs: dict[str, Any] = field(default_factory=dict)
    companion_goal: dict[str, Any] = field(default_factory=dict)
    companion_execution: dict[str, Any] = field(default_factory=dict)
    companion_auto: dict[str, Any] = field(default_factory=dict)
    world_memory: dict[str, Any] = field(default_factory=dict)
    world_memory_autowrite: dict[str, Any] = field(default_factory=dict)
    memory_shadow: dict[str, Any] = field(default_factory=dict)
    memory_needs_bias: dict[str, Any] = field(default_factory=dict)
    companion_probe_error: str = ""
    companion_probe_url: str = ""
    companion_last_probe: float = 0.0
    hidden_noise: int = 0
    started_at: float = field(default_factory=time.time)
    events_version: int = 0
    _view_cache: tuple[Any, list[LogEvent]] | None = None

    def feed_line(self, line: str) -> None:
        from .console_formatting import repair_mojibake, strip_ansi
        from .console_helpers import parse_log_line, infer_channel

        line = repair_mojibake(line.rstrip("\r\n"))
        if not line or line.startswith("--- robot subprocess"):
            return
        self.raw_lines.append(line)
        ev = parse_log_line(line)
        if ev is not None:
            self.feed_event(ev)
        else:
            clean = strip_ansi(line).strip()
            if clean:
                level = "INFO"
                if any(x in clean for x in ("ERROR", "Traceback", "Exception", "failed", "Error:")):
                    level = "ERROR"
                elif any(x in clean for x in ("WARNING", "WARN", "DeprecationWarning")):
                    level = "WARN"
                pseudo = LogEvent(
                    time=time.strftime("%H:%M:%S"),
                    level=level,
                    source="runtime",
                    channel=infer_channel("runtime", clean),
                    message=clean,
                    raw=line,
                )
                self.feed_event(pseudo)

    def feed_event(self, ev: LogEvent) -> None:
        from .console_formatting import crop

        self.events.append(ev)
        self.events_version += 1
        lvl = ev.level.upper().replace("WARNING", "WARN")
        self.counts[lvl] += 1
        msg = ev.message
        low = msg.lower()
        if any(h.lower() in low for h in NOISE_HINTS):
            self.hidden_noise += 1
        for match in HTTP_RE.finditer(ev.raw):
            endpoint = match.group("path")
            self.endpoints[endpoint] += 1
        for match in REMOTE_RE.finditer(ev.raw):
            self.remote_hosts[match.group(0)] += 1
        for needle, chan, desc in BLOCKER_HINTS:
            if needle.lower() in low:
                self.blockers[needle] = (chan, desc, ev.time)
        for service, rules in SERVICE_RULES.items():
            for needle, state, detail in rules:
                if needle.lower() in low:
                    self.services[service] = ServiceStatus(service, state, detail, ev.time)
        if ev.channel in self.services and LEVEL_ORDER.get(lvl, 0) >= 40:
            self.services[ev.channel] = ServiceStatus(ev.channel, "ERR", crop(msg, 44), ev.time)
        elif ev.channel in self.services and LEVEL_ORDER.get(lvl, 0) >= 30:
            old = self.services.get(ev.channel, ServiceStatus(ev.channel))
            if old.state not in {"ERR"}:
                self.services[ev.channel] = ServiceStatus(ev.channel, "WARN", crop(msg, 44), ev.time)

    @property
    def uptime(self) -> str:
        secs = int(time.time() - self.started_at)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def health_summary(self) -> tuple[int, int, int]:
        errors = sum(1 for s in self.services.values() if s.state == "ERR")
        warns = sum(1 for s in self.services.values() if s.state == "WARN")
        oks = sum(1 for s in self.services.values() if s.state == "OK")
        return errors, warns, oks


@dataclass
class UIState:
    root: Path
    active_tab: int = 0
    filter_text: str = ""
    log_view: str = "full"
    project_search: str = ""
    project_results: list[SearchResult] = field(default_factory=list)
    selected_config: int = 0
    selected_event: int = 0
    scroll: int = 0
    command_mode: str = ""
    command_buffer: str = ""
    pending_key: str = ""
    message: str = ""
    paused: bool = False
    profile: str = "pc-test"
    last_render: float = 0.0


class LogTailer:
    def __init__(self, root: Path, start_at_end: bool = False) -> None:
        self.root = root
        self.files = [
            root / "logs" / "sentry.log",
            root / "logs" / "tui.log",
            root / "logs" / "runtime_stdout.log",
        ]
        self.positions: dict[Path, int] = {}
        if start_at_end:
            for path in self.files:
                try:
                    if path.exists():
                        self.positions[path] = path.stat().st_size
                except Exception:
                    pass

    def read_new(self, snapshot: Snapshot) -> None:
        primary = self.root / "logs" / "sentry.log"
        if primary.exists() and primary.stat().st_size > 0:
            target_files = [primary]
        else:
            target_files = [f for f in self.files if f.exists()]

        for path in target_files:
            try:
                size = path.stat().st_size
                pos = self.positions.get(path, 0)
                if pos > size:
                    pos = 0
                if pos == 0 and size > MAX_TAIL_BYTES:
                    pos = size - MAX_TAIL_BYTES
                if pos >= size:
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(pos)
                    for line in fh:
                        snapshot.feed_line(line)
                    self.positions[path] = fh.tell()
            except Exception as exc:
                pass
