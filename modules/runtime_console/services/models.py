from __future__ import annotations

import os
import re
import shutil
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT = True
RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE = "pc_dev_robot_preview_status_classifier"

APP = "SENTRYBOT"
TITLE = "SENTRYBOT CONTROL CENTER"
VERSION = "tui-v16-memory-bias"
DEFAULT_REFRESH = 0.18
MAX_TAIL_BYTES = 2_000_000
MAX_SEARCH_FILE_BYTES = 900_000
SEARCH_EXTS = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".log", ".ini", ".toml"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

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

LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
TABS = ["Overview", "Logs", "Signals", "Config", "Search", "Companion", "Expression", "Camera", "Help"]
PC_EXPECTED_HINTS = (
    "ESP bridge unreachable",
    "ESP bridge unreachable - expected on PC tests",
    "animate degraded",
    "pose step skipped",
    "Vosk TR model missing",
    "Vosk model directory not found",
    "Turkish Vosk model is missing",
    "Vosk model directory missing",
    "Speech/STT unavailable",
    "speech stt unavailable",
    "speech start rejected",
    "stt_unavailable",
    "openwakeword unavailable",
    "piper unavailable",
    "Piper voice model is missing",
    "Piper model missing",
    "piper.model_path not found",
    "TR-dfki",
    "OpenCV not available",
    "OpenCV face cascade disabled",
    "face cascade disabled",
    "No speak_fn set",
    "no speaker function",
    "Speech arbiter has no speaker function",
    "LLM chat unavailable",
    "LLM provider unavailable",
    "Ollama unavailable",
    "Ollama daemon unavailable",
    "remote Ollama unavailable",
    "remote AI unavailable",
    "model unavailable",
    "model_available:false",
    "model_available=false",
    "daemon_ok:false",
    "daemon_ok=false",
    "api/tags",
    "Max retries exceeded",
    "ConnectTimeoutError",
    "Connection refused",
    "Connection to 127.0.0.1 timed out",
    "Connection to 192.",
    "qwen3.5:9b",
)

SERVICE_RULES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "CORE": (
        ("Application startup complete", "OK", "runtime ready"),
        ("Loaded gateway config", "OK", "gateway config loaded"),
        ("Shutdown", "IDLE", "stopping"),
    ),
    "AI": (
        ("LLM provider client ready", "OK", "provider ready"),
        ("Vision LLM client initialized", "OK", "vision provider ready"),
        ("api_key is missing", "ERR", "Google API key missing"),
        ("LLM chat failed", "ERR", "LLM endpoint failed"),
        ("Provider client init failed", "ERR", "provider init failed"),
        ("fallback to ollama", "WARN", "fallback provider"),
    ),
    "VISION": (
        ("Vision LLM client initialized", "OK", "vision provider ready"),
        ("Remote mode: waiting", "IDLE", "remote result mode"),
        ("OpenCV not available", "WARN", "OpenCV/cascade disabled"),
        ("VLM client init failed", "ERR", "VLM init failed"),
        ("Loaded 3 person records", "OK", "person DB loaded"),
    ),
    "AUDIO": (
        ("wakeword listening started", "OK", "wakeword listening"),
        ("SpeechArbiter started", "OK", "speech arbiter"),
        ("Vosk TR model missing", "ERR", "TR Vosk model missing"),
        ("Vosk model directory not found", "ERR", "Vosk model missing"),
        ("Speech/STT unavailable", "ERR", "STT model missing"),
        ("speech stt unavailable", "ERR", "STT unavailable"),
        ("speech start rejected", "WARN", "STT unavailable"),
        ("openwakeword unavailable", "WARN", "openwakeword fallback"),
    ),
    "TTS": (
        ("First audio", "OK", "audio started"),
        ("piper unavailable", "WARN", "Piper model missing"),
        ("dummy", "WARN", "test-tone voice compatibility warning"),
    ),
    "MOVE": (
        ("ESP bridge unreachable", "WARN", "ESP bridge unreachable"),
        ("animate degraded", "WARN", "animation degraded"),
        ("pose step skipped", "WARN", "pose skipped"),
    ),
    "CONFIG": (
        ("changeme", "WARN", "default token"),
        ("no api_keys configured", "WARN", "gateway API keys missing"),
    ),
}

CHANNEL_HINTS = {
    "AI": ("agent", "ollama", "google", "gemini", "llm", "provider"),
    "VISION": ("vlm", "vision", "camera", "opencv", "face", "qwen", "imx"),
    "AUDIO": ("wakeword", "speech", "vosk", "microphone", "audio"),
    "TTS": ("speak", "tts", "piper", "voice", "glados"),
    "MOVE": ("arduino", "esp", "servo", "animate", "motor", "piservo"),
    "FACE": ("oled", "neopixel", "expression", "emotion"),
    "MEMORY": ("memory", "rag", "social", "slam", "map"),
}

NOISE_HINTS = (
    "Starting new HTTP connection",
    "GET /state/get",
    "GET /speech/last",
    "GET /speech/direction",
    "GET /vlm/context/latest",
    "GET /vlm/results/latest",
    "POST /arduino/request",
    "POST /interactions/event",
    "POST /interactions/effect",
    "POST /neopixel/animate",
    "POST /oled_faces/manual",
)

BLOCKER_HINTS = (
    ("piper unavailable", "TTS", "Piper voice model is missing"),
    ("Vosk TR model missing", "AUDIO", "Turkish Vosk model is missing"),
    ("Vosk model directory not found", "AUDIO", "Vosk model directory missing"),
    ("ESP bridge unreachable", "MOVE", "ESP bridge unreachable - expected on PC tests"),
    ("OpenCV not available", "VISION", "OpenCV face cascade disabled"),
    ("api_key is missing", "AI", "Google API key missing"),
    ("changeme", "CONFIG", "Default security token still configured"),
    ("No speak_fn set", "TTS", "Speech arbiter has no speaker function"),
    ("Speech arbiter has no speaker function", "TTS", "Speech arbiter has no speaker function"),
)


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

    def feed_line(self, line: str) -> None:
        line = repair_mojibake(line.rstrip("\n"))
        if not line:
            return
        self.raw_lines.append(line)
        ev = parse_log_line(line)
        if ev is not None:
            self.feed_event(ev)
        else:
            if any(x in line for x in ("WARNING", "ERROR", "Runtime console initialized")):
                pseudo = LogEvent(
                    time=time.strftime("%H:%M:%S"),
                    level="INFO",
                    source="stdout",
                    channel="CORE",
                    message=strip_ansi(line),
                    raw=line,
                )
                self.feed_event(pseudo)

    def feed_event(self, ev: LogEvent) -> None:
        self.events.append(ev)
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


def infer_channel(source: str, msg: str) -> str:
    src = (source + " " + msg).lower()
    for channel, hints in CHANNEL_HINTS.items():
        if any(h in src for h in hints):
            return channel
    return "CORE" if "gateway" in src or "run_robot" in src else "SYS"


def parse_log_line(line: str) -> LogEvent | None:
    plain = safe_text(strip_ansi(line).strip())
    m = LOG_RE.match(plain)
    if m:
        source = m.group("src").strip()
        msg = m.group("msg").strip()
        channel = infer_channel(source, msg)
        return LogEvent(m.group("time"), m.group("level"), source, channel, msg, line)
    m = COMPACT_RE.match(plain)
    if m:
        level = m.group("level").strip().replace("WARN ", "WARN")
        channel = m.group("chan").strip()
        return LogEvent(m.group("time"), level, channel.lower(), channel, m.group("msg").strip(), line)
    return None


class LogTailer:
    def __init__(self, root: Path, start_at_end: bool = False) -> None:
        self.root = root
        self.files = [root / "logs" / "sentry.log", root / "logs" / "runtime_stdout.log"]
        self.positions: dict[Path, int] = {}
        if start_at_end:
            for path in self.files:
                try:
                    if path.exists():
                        self.positions[path] = path.stat().st_size
                except Exception:
                    pass

    def read_new(self, snapshot: Snapshot) -> None:
        for path in self.files:
            if not path.exists():
                continue
            try:
                size = path.stat().st_size
                pos = self.positions.get(path, 0)
                if pos > size:
                    pos = 0
                if pos == 0 and size > MAX_TAIL_BYTES:
                    pos = size - MAX_TAIL_BYTES
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(pos)
                    for line in fh:
                        snapshot.feed_line(line)
                    self.positions[path] = fh.tell()
            except Exception as exc:
                snapshot.feed_event(
                    LogEvent(
                        time.strftime("%H:%M:%S"),
                        "WARN",
                        "tui",
                        "SYS",
                        f"could not read {path.name}: {exc}",
                        "",
                    )
                )


@dataclass
class UIState:
    root: Path
    active_tab: int = 0
    filter_text: str = ""
    log_view: str = "human"
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


def is_pc_test(root: Path) -> bool:
    if os.name == "nt":
        return True
    model = Path("/proc/device-tree/model")
    if not model.exists():
        return True
    try:
        text = model.read_text(errors="ignore").lower()
        return "raspberry" not in text
    except Exception:
        return True


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


def filter_events(events: Iterable[LogEvent], text: str, include_debug: bool) -> list[LogEvent]:
    result: list[LogEvent] = []
    text_l = text.lower().strip()
    for ev in events:
        if not include_debug and ev.level.upper() == "DEBUG":
            continue
        if text_l and text_l not in (ev.raw + ev.message + ev.source + ev.channel).lower():
            continue
        result.append(ev)
    return result


def is_low_value_startup(ev: LogEvent) -> bool:
    msg = ev.message.lower()
    if ev.level.upper() == "DEBUG":
        return True
    if any(h.lower() in msg for h in NOISE_HINTS):
        return True
    if ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"}:
        return False
    startup_fragments = (
        "module ", " mounted", "wired to", "event bridge mounted",
        "application startup complete", "started server process",
        "waiting for application startup", "finished server process",
        "loaded gateway config", "available modules", "press ctrl+c",
    )
    if any(x in msg for x in startup_fragments):
        keep = ("provider client ready", "robot is bored", "idle behavior", "companion", "vision llm", "speecharbiter")
        return not any(k in msg for k in keep)
    return False


def is_pc_expected(desc: str, message: str = "") -> bool:
    text = (desc + " " + message).lower()
    return any(h.lower() in text for h in PC_EXPECTED_HINTS)


def service_is_pc_expected(name: str, svc: ServiceStatus) -> bool:
    service_text = f"{name} {svc.state} {svc.detail}".lower()
    if name == "MOVE" and any(
        x in service_text for x in ("esp bridge unreachable", "animate degraded", "pose skipped", "pose step skipped")
    ):
        return True
    if name == "TTS" and any(
        x in service_text for x in ("piper", "dummy", "no speaker", "speech arbiter", "tts disabled")
    ):
        return True
    if name == "AUDIO" and any(
        x in service_text for x in ("vosk", "openwakeword", "wakeword fallback", "model directory missing")
    ):
        return True
    if name == "VISION" and any(
        x in service_text for x in ("opencv", "cascade", "camera off", "remote-only", "camera disabled")
    ):
        return True
    if name == "AI" and any(
        x in service_text
        for x in (
            "llm chat unavailable",
            "llm provider unavailable",
            "ollama unavailable",
            "ollama daemon unavailable",
            "remote ollama unavailable",
            "remote ai unavailable",
            "provider unavailable",
            "model unavailable",
            "model_available:false",
            "model_available=false",
            "daemon_ok:false",
            "daemon_ok=false",
            "api/tags",
            "max retries exceeded",
            "connecttimeouterror",
            "connection refused",
            "timed out",
            "qwen3.5:9b",
        )
    ):
        return True
    return False


def event_is_pc_expected(ev: LogEvent) -> bool:
    return is_pc_expected(ev.message) or is_pc_expected(ev.source + " " + ev.message)


def health_summary_for(snapshot: Snapshot, ui: UIState) -> tuple[int, int, int, int]:
    errors = 0
    warns = 0
    oks = 0
    pc_expected = 0
    for name, svc in snapshot.services.items():
        state = svc.state.upper().replace("WARNING", "WARN").replace("ERROR", "ERR")
        if ui.profile == "pc-test" and state in {"WARN", "ERR", "CRITICAL"} and service_is_pc_expected(name, svc):
            pc_expected += 1
        elif state in {"ERR", "CRITICAL"}:
            errors += 1
        elif state == "WARN":
            warns += 1
        elif state == "OK":
            oks += 1
    return errors, warns, oks, pc_expected


def events_for_view(snapshot: Snapshot, ui: UIState, include_debug: bool | None = None) -> list[LogEvent]:
    if include_debug is None:
        include_debug = bool(ui.filter_text) and ui.filter_text.lower() in {"debug", "all", "*"}
    filter_text = ui.filter_text if ui.filter_text.lower() not in {"debug", "all", "*"} else ""
    events = filter_events(snapshot.events, filter_text, include_debug)
    view = ui.log_view.lower()
    if view == "warn":
        events = [ev for ev in events if ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"}]
    elif view == "human" and not filter_text:
        events = [ev for ev in events if not is_low_value_startup(ev)]
        if ui.profile == "pc-test":
            events = [
                ev
                for ev in events
                if not (
                    ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"}
                    and event_is_pc_expected(ev)
                )
            ]
    return events


def current_log_events(snapshot: Snapshot, ui: UIState, include_debug: bool | None = None) -> list[LogEvent]:
    return events_for_view(snapshot, ui, include_debug=include_debug)


def newest_first_events(snapshot: Snapshot, ui: UIState) -> list[LogEvent]:
    return list(reversed(current_log_events(snapshot, ui)))


def selected_event(snapshot: Snapshot, ui: UIState) -> LogEvent | None:
    events = newest_first_events(snapshot, ui)
    if not events:
        return None
    idx = min(max(0, ui.selected_event), len(events) - 1)
    ui.selected_event = idx
    return events[idx]


def suggested_fix(ev: LogEvent | None, ui: UIState) -> list[str]:
    if ev is None:
        return ["No event selected."]
    msg = ev.message.lower()
    out: list[str] = []
    if "piper unavailable" in msg or "model_path not found" in msg:
        out += [
            "TTS model missing.",
            "PC test: expected until Piper model is installed.",
            "Robot: install or point piper.model_path to a real .onnx.",
        ]
    elif "vosk tr model missing" in msg or "vosk model directory" in msg:
        out += [
            "Speech model missing.",
            "PC test: expected until Vosk models are present.",
            "Robot: run tools/install_vosk_tr.py and add EN model if wakeword fallback uses it.",
        ]
    elif "esp bridge unreachable" in msg:
        out += [
            "ESP bridge is unreachable.",
            "PC test: expected when robot hardware is absent.",
            "Robot: check ESP IP, power and network route.",
        ]
    elif "opencv not available" in msg:
        out += [
            "OpenCV/cascade path disabled.",
            "PC test: install opencv-python only if local vision tests need it.",
        ]
    elif "changeme" in msg or "auth_token" in msg:
        out += ["Default token still configured.", "Config: edit config/agent.yaml and replace changeme values."]
    elif "api_key" in msg:
        out += ["Google provider key missing.", "Config: set google_ai_studio.api_key or GOOGLE_API_KEY."]
    else:
        out += ["No specific fix rule yet.", "Use Logs tab with / filter or Search tab with s."]
    if ui.profile == "pc-test" and is_pc_expected(" ".join(out), ev.message):
        out.insert(0, "PC TEST MODE: this is expected on the laptop.")
    return out


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


def list_config_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for folder in [root / "config", root / "modules"]:
        if not folder.exists():
            continue
        for path in folder.rglob("*.yml"):
            if ".sentrybot_backups" not in path.parts and "__pycache__" not in path.parts:
                files.append(path)
        for path in folder.rglob("*.yaml"):
            if ".sentrybot_backups" not in path.parts and "__pycache__" not in path.parts:
                files.append(path)
    return sorted(set(files), key=lambda p: str(p.relative_to(root)).lower())[:250]


def preview_file(path: Path, max_lines: int) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return [f"cannot read: {exc}"]
    return text[:max_lines]


def parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if raw.lower() in {"null", "none"}:
        return None
    try:
        return int(raw)
    except Exception:
        pass
    try:
        return float(raw)
    except Exception:
        pass
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        return raw[1:-1]
    return raw


def set_nested(data: dict[str, Any], dotted: str, value: Any) -> None:
    cur: dict[str, Any] = data
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        raise ValueError("empty key")
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def edit_yaml(root: Path, file_index: int, key: str, value: str) -> str:
    if yaml is None:
        return "PyYAML not available; config editing disabled"
    files = list_config_files(root)
    if not files:
        return "no yaml files found"
    path = files[min(max(0, file_index), len(files) - 1)]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        if not isinstance(data, dict):
            data = {}
        set_nested(data, key, parse_scalar(value))
        backup_dir = root / ".sentrybot_backups" / ("tui_config_" + time.strftime("%Y%m%d_%H%M%S"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        rel = path.relative_to(root)
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return f"saved {rel}: {key}={value}"
    except Exception as exc:
        return f"edit failed: {exc}"


def project_search(root: Path, query: str, limit: int = 200) -> list[SearchResult]:
    q = query.lower().strip()
    if not q:
        return []
    results: list[SearchResult] = []
    skip_dirs = {".git", ".venv", "venv", "__pycache__", ".sentrybot_backups", "node_modules"}
    for path in root.rglob("*"):
        if len(results) >= limit:
            break
        if not path.is_file() or path.suffix.lower() not in SEARCH_EXTS:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if q in line.lower():
                    results.append(SearchResult(str(path.relative_to(root)).replace("\\", "/"), idx, line.strip()))
                    if len(results) >= limit:
                        break
        except Exception:
            continue
    return results


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
