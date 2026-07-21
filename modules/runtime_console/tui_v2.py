from __future__ import annotations
RUNTIME_CONSOLE_PREVIEW_WARNING_COMPATIBILITY_CONTRACT = True
RUNTIME_CONSOLE_PREVIEW_WARNING_ROLE = "pc_dev_robot_preview_status_classifier"


import argparse
import atexit
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

APP = "SENTRYBOT"
TITLE = "SENTRYBOT CONTROL CENTER"
VERSION = "tui-v16-memory-bias"
DEFAULT_REFRESH = 0.18
MAX_TAIL_BYTES = 2_000_000
MAX_SEARCH_FILE_BYTES = 900_000
SEARCH_EXTS = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".log", ".ini", ".toml"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# Windows CMD and some terminals mis-decode UTF-8 box drawing as mojibake
# (for example: "â”€" instead of a horizontal line).  The TUI defaults to a
# safe ASCII renderer and also repairs common mojibake from old log files.
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
    # First try to undo UTF-8 bytes interpreted as Windows-1252/Latin-1.
    if "â" in text or "Ã" in text or "Â" in text:
        for enc in ("cp1252", "latin1"):
            try:
                fixed = text.encode(enc, errors="ignore").decode("utf-8", errors="ignore")
                if fixed and fixed != text and fixed.count("�") <= text.count("�"):
                    text = fixed
                    break
            except Exception:
                pass
    return text.replace("�", "?")

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

LOG_RE = re.compile(r"^(?P<time>\d\d:\d\d:\d\d)\s+\|\s+(?P<level>[A-Z]+)\s+\|\s+(?P<src>[^|]+)\|\s+(?P<msg>.*)$")
COMPACT_RE = re.compile(r"^(?P<time>\d\d:\d\d:\d\d)\s+(?P<chan>[A-Z_]+)\s+\[(?P<level>[^\]]+)\]\s+(?P<msg>.*)$")
HTTP_RE = re.compile(r'"(?P<method>GET|POST|PUT|PATCH|DELETE)\s+(?P<path>/[^\s?\"]+)')
REMOTE_RE = re.compile(r"\b(?P<host>127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|localhost):(?P<port>\d+)\b")

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


def enable_virtual_terminal() -> None:
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
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
    # Hide user-specific long Windows paths in the UI. Full paths stay in logs.
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
    services: dict[str, ServiceStatus] = field(default_factory=lambda: {k: ServiceStatus(k) for k in ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE", "CONFIG"]})
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
    companion_behavior_loop: dict[str, Any] = field(default_factory=dict)
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
            # Captured old dashboard boxes are kept as raw file detail, not promoted.
            if any(x in line for x in ("WARNING", "ERROR", "Runtime console initialized")):
                pseudo = LogEvent(time=time.strftime("%H:%M:%S"), level="INFO", source="stdout", channel="CORE", message=strip_ansi(line), raw=line)
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
                snapshot.feed_event(LogEvent(time.strftime("%H:%M:%S"), "WARN", "tui", "SYS", f"could not read {path.name}: {exc}", ""))



class RobotProcess:
    def __init__(self, root: Path, enabled: bool, profile: str | None = None) -> None:
        self.root = root
        self.enabled = enabled
        self.proc: subprocess.Popen[str] | None = None
        self.output_log = root / "logs" / "runtime_stdout.log"
        self.thread: threading.Thread | None = None
        self.profile = str(profile or "")

    def start(self) -> str:
        if not self.enabled:
            return "attached to existing logs"
        (self.root / "logs").mkdir(exist_ok=True)
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("SENTRYBOT_AUDIO_PROMPT", "0")
        env["SENTRYBOT_CONSOLE_MODE"] = "off"
        env["SENTRYBOT_RUNTIME_CONSOLE"] = "off"
        env["SENTRYBOT_TUI_MODE"] = "1"
        if self.profile in {"pc", "pc-test"}:
            env["SENTRYBOT_PC_TEST"] = "1"
            env["SENTRYBOT_PROFILE"] = "pc-test"
        try:
            if self.output_log.exists():
                prev = self.output_log.with_suffix(".prev.log")
                self.output_log.replace(prev)
        except Exception:
            pass
        cmd = [sys.executable, "-u", "scripts/run_robot.py"]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()
        return "robot subprocess started"

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        with self.output_log.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"\n--- robot subprocess started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            for line in self.proc.stdout:
                fh.write(line)
                fh.flush()

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    @property
    def status(self) -> str:
        if self.proc is None:
            return "attached"
        code = self.proc.poll()
        if code is None:
            return f"running pid={self.proc.pid}"
        return f"stopped code={code}"


class KeyReader:
    def __init__(self) -> None:
        self.windows = os.name == "nt"
        self.old_term: Any = None
        if not self.windows:
            import termios
            import tty
            self.termios = termios
            self.tty = tty

    def __enter__(self) -> "KeyReader":
        if not self.windows and sys.stdin.isatty():
            self.old_term = self.termios.tcgetattr(sys.stdin)
            self.tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_: Any) -> None:
        if not self.windows and self.old_term is not None:
            self.termios.tcsetattr(sys.stdin, self.termios.TCSADRAIN, self.old_term)

    def read(self) -> str | None:
        if self.windows:
            import msvcrt
            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                nxt = msvcrt.getwch()
                return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "G": "HOME", "O": "END", "I": "PGUP", "Q": "PGDN"}.get(nxt)
            if ch == "\r":
                return "ENTER"
            if ch == "\x08":
                return "BACKSPACE"
            if ch == "\x1b":
                return "ESC"
            return ch
        import select
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "UP", "[B": "DOWN", "[D": "LEFT", "[C": "RIGHT", "[5": "PGUP", "[6": "PGDN"}.get(seq, "ESC")
        if ch in ("\n", "\r"):
            return "ENTER"
        if ch in ("\x7f", "\b"):
            return "BACKSPACE"
        return ch


@dataclass
class UIState:
    root: Path
    active_tab: int = 0
    filter_text: str = ""
    log_view: str = "human"  # human, full, warn
    project_search: str = ""
    project_results: list[SearchResult] = field(default_factory=list)
    selected_config: int = 0
    selected_event: int = 0
    scroll: int = 0
    command_mode: str = ""  # filter, command, edit_key, edit_value, project_search
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
    # Keep the default renderer ASCII-safe. Unicode borders are intentionally
    # not emitted because Windows CMD often renders them as mojibake.
    return ("+", "+", "+", "+", "-", "|")


def box(title: str, lines: list[str], width: int, height: int | None, pal: Palette, ascii_mode: bool = False) -> list[str]:
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


def draw_header(width: int, snapshot: Snapshot, ui: UIState, robot_status: str, pal: Palette) -> str:
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    profile = "PC TEST" if ui.profile == "pc-test" else "ROBOT"
    left = pal.bold(f" {APP} CONTROL CENTER ")
    mid = f"{VERSION} | {profile} | {robot_status} | up {snapshot.uptime}"
    right = f"OK:{oks} PC:{pc_count} WARN:{warns} ERR:{errs}" if pc_count else f"OK:{oks} WARN:{warns} ERR:{errs}"
    room = width - visible_len(left) - len(mid) - len(right) - 2
    if room < 1:
        mid = crop(mid, max(10, width - visible_len(left) - len(right) - 4))
        room = width - visible_len(left) - len(mid) - len(right) - 2
    return fit(left + " " + mid + " " * max(1, room) + right, width)


def draw_sidebar(height: int, width: int, ui: UIState, snapshot: Snapshot, pal: Palette, ascii_mode: bool) -> list[str]:
    lines: list[str] = []
    for idx, tab in enumerate(TABS):
        prefix = f"{idx+1}" if idx < 9 else " "
        marker = ">" if idx == ui.active_tab else " "
        label = f" {marker} {prefix} {tab}"
        lines.append(pal.cyan(label) if idx == ui.active_tab else label)
    lines.append("")
    lines.append(pal.dim("Health"))
    for name in ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE"]:
        svc = snapshot.services.get(name, ServiceStatus(name))
        state = "PC" if ui.profile == "pc-test" and service_is_pc_expected(name, svc) else svc.state
        lines.append(f" {name:<7} {pal.level(state):<12}")
    lines.append("")
    lines.append(pal.dim("Hotkeys"))
    for item in ["/ filter", "v view", "s search", "e edit", ": command", "r refresh", "q quit"]:
        lines.append(" " + item)
    return box("NAVIGATOR", lines, width, height, pal, ascii_mode)


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
        # Keep semantically useful lines even if they contain ordinary startup words.
        keep = ("provider client ready", "robot is bored", "idle behavior", "companion", "vision llm", "speecharbiter")
        return not any(k in msg for k in keep)
    return False


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
                ev for ev in events
                if not (ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"} and event_is_pc_expected(ev))
            ]
    return events



def is_pc_expected(desc: str, message: str = "") -> bool:
    text = (desc + " " + message).lower()
    return any(h.lower() in text for h in PC_EXPECTED_HINTS)




def service_is_pc_expected(name: str, svc: ServiceStatus) -> bool:
    service_text = f"{name} {svc.state} {svc.detail}".lower()
    if name == "MOVE" and any(x in service_text for x in ("esp bridge unreachable", "animate degraded", "pose skipped", "pose step skipped")):
        return True
    if name == "TTS" and any(x in service_text for x in ("piper", "dummy", "no speaker", "speech arbiter", "tts disabled")):
        return True
    if name == "AUDIO" and any(x in service_text for x in ("vosk", "openwakeword", "wakeword fallback", "model directory missing")):
        return True
    if name == "VISION" and any(x in service_text for x in ("opencv", "cascade", "camera off", "remote-only", "camera disabled")):
        return True
    if name == "AI" and any(x in service_text for x in (
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
    )):
        return True
    return False


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


def event_is_pc_expected(ev: LogEvent) -> bool:
    return is_pc_expected(ev.message) or is_pc_expected(ev.source + " " + ev.message)

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
        out += ["TTS model missing.", "PC test: expected until Piper model is installed.", "Robot: install or point piper.model_path to a real .onnx."]
    elif "vosk tr model missing" in msg or "vosk model directory" in msg:
        out += ["Speech model missing.", "PC test: expected until Vosk models are present.", "Robot: run tools/install_vosk_tr.py and add EN model if wakeword fallback uses it."]
    elif "esp bridge unreachable" in msg:
        out += ["ESP bridge is unreachable.", "PC test: expected when robot hardware is absent.", "Robot: check ESP IP, power and network route."]
    elif "opencv not available" in msg:
        out += ["OpenCV/cascade path disabled.", "PC test: install opencv-python only if local vision tests need it."]
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


def _gateway_base_url() -> str:
    return os.getenv("SENTRYBOT_TUI_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def _json_get(path: str, timeout: float = 0.35) -> tuple[dict[str, Any] | None, str]:
    url = _gateway_base_url() + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local diagnostics only
            raw = resp.read(256_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {"value": data}, ""
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read(128_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                return data, f"HTTP {exc.code}"
        except Exception:
            pass
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, exc.__class__.__name__ + ": " + str(exc)


def refresh_camera_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    if not force and (now - float(snapshot.camera_last_probe or 0.0)) < 2.5:
        return
    snapshot.camera_last_probe = now
    snapshot.camera_probe_url = _gateway_base_url()
    status, err = _json_get("/camera/status")
    if status is not None:
        snapshot.camera_status = status
        snapshot.camera_probe_error = ""
    else:
        snapshot.camera_probe_error = err
    latest, err2 = _json_get("/camera/onsensor/latest")
    if latest is not None:
        snapshot.camera_onsensor = latest
    elif not snapshot.camera_probe_error:
        snapshot.camera_probe_error = err2


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


def render_camera(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    status = snapshot.camera_status or {}
    onsensor = snapshot.camera_onsensor or {}
    capture = status.get("capture") if isinstance(status.get("capture"), dict) else {}
    imx = status.get("imx500") if isinstance(status.get("imx500"), dict) else {}
    bus = status.get("onsensor") if isinstance(status.get("onsensor"), dict) else {}
    latest_snapshot = onsensor.get("snapshot") if isinstance(onsensor.get("snapshot"), dict) else None
    lines: list[str] = []
    lines.append(pal.bold("Camera / IMX500 status"))
    lines.append(f"gateway: {snapshot.camera_probe_url or _gateway_base_url()}")
    if snapshot.camera_probe_error and not status:
        lines.append(pal.yellow("probe: " + crop(snapshot.camera_probe_error, max(10, width - 8))))
        lines.append("attach mode needs an already running gateway")
    else:
        lines.append("probe: " + (pal.green("ok") if not snapshot.camera_probe_error else pal.yellow(snapshot.camera_probe_error)))
    lines.append("")
    lines.append(pal.bold("Capture"))
    render_kv(lines, "enabled/live", f"{bool(status.get('enabled'))}/{bool(status.get('live'))}", width)
    render_kv(lines, "backend", capture.get("backend"), width)
    render_kv(lines, "source", capture.get("source"), width)
    render_kv(lines, "running/frame", f"{capture.get('running')}/{capture.get('has_frame')}", width)
    render_kv(lines, "opencv", dict_get(capture, "opencv", "available"), width)
    render_kv(lines, "picamera2", dict_get(capture, "picamera2", "available"), width)
    lines.append("")
    lines.append(pal.bold("IMX500"))
    render_kv(lines, "enabled/available", f"{imx.get('enabled')}/{imx.get('available')}", width)
    render_kv(lines, "running", imx.get("running"), width)
    render_kv(lines, "reason", imx.get("reason"), width)
    render_kv(lines, "model/labels", f"{imx.get('model_path_exists')}/{imx.get('labels_path_exists')}", width)
    render_kv(lines, "last_publish_age_s", imx.get("last_publish_age_s"), width)
    lines.append("")
    lines.append(pal.bold("On-sensor bus"))
    render_kv(lines, "attached/latest", f"{bus.get('attached')}/{bus.get('has_latest')}", width)
    render_kv(lines, "published/subs", f"{bus.get('published_count')}/{bus.get('subscribers')}", width)
    render_kv(lines, "latest_age_s", bus.get("latest_age_s"), width)
    if latest_snapshot:
        dets = latest_snapshot.get("detections") or []
        lines.append(pal.bold(f"Latest detections: {len(dets)}"))
        for det in dets[: max(0, height - len(lines) - 1)]:
            if not isinstance(det, dict):
                continue
            label = det.get("label", "object")
            score = det.get("score", 0)
            lines.append(f" - {label:<16} {score}")
    else:
        lines.append("no on-sensor snapshot yet")
    if height > 26:
        # Extra diagnostics appear only when the terminal has room, so the main truth lines stay visible.
        picam_err = dict_get(capture, "picamera2", "import_error")
        if picam_err:
            lines.append("")
            render_kv(lines, "picamera2_error", picam_err, width)
        if imx.get("model_path"):
            render_kv(lines, "model_path", imx.get("model_path"), width)
    return lines[:height]


def refresh_expression_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    if not force and (now - float(snapshot.expression_last_probe or 0.0)) < 1.5:
        return
    snapshot.expression_last_probe = now
    snapshot.expression_probe_url = _gateway_base_url()
    state, err = _json_get("/expression/state", timeout=0.35)
    if state is not None:
        snapshot.expression_state = state
        snapshot.expression_probe_error = ""
    else:
        snapshot.expression_probe_error = err
    status, err2 = _json_get("/expression/status", timeout=0.35)
    if status is not None:
        snapshot.expression_status = status
    elif not snapshot.expression_probe_error:
        snapshot.expression_probe_error = err2
    history, _ = _json_get("/expression/history?limit=12", timeout=0.35)
    if history is not None:
        snapshot.expression_history = history



def refresh_expression_output_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    last = float(getattr(snapshot, "expression_output_last_probe", 0.0) or 0.0)
    if not force and (now - last) < 1.5:
        return
    snapshot.expression_output_last_probe = now
    status, err = _json_get("/expression/output/status", timeout=0.35)
    if status is not None:
        snapshot.expression_output_status = status
        snapshot.expression_output_probe_error = ""
    else:
        snapshot.expression_output_probe_error = err
    plan, err2 = _json_get("/expression/output/plan", timeout=0.45)
    if plan is not None:
        snapshot.expression_output_plan = plan
        if not snapshot.expression_output_probe_error:
            snapshot.expression_output_probe_error = ""
    elif not snapshot.expression_output_probe_error:
        snapshot.expression_output_probe_error = err2

def _expression_core(snapshot: Snapshot) -> dict[str, Any]:
    state_payload = snapshot.expression_state or {}
    state = state_payload.get("state") if isinstance(state_payload.get("state"), dict) else {}
    status = snapshot.expression_status or {}
    if not state and isinstance(status, dict):
        state = {
            "emotion": status.get("emotion"),
            "arousal": status.get("arousal"),
            "attention": status.get("attention"),
        }
    targets = state_payload.get("targets") if isinstance(state_payload.get("targets"), dict) else status.get("targets") if isinstance(status.get("targets"), dict) else {}
    return {"state": state or {}, "targets": targets or {}, "payload": state_payload, "status": status}


def render_expression(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    core = _expression_core(snapshot)
    st = core["state"]
    targets = core["targets"]
    history = snapshot.expression_history.get("history") if isinstance(snapshot.expression_history, dict) else []
    event_counts = core["payload"].get("event_counts") if isinstance(core["payload"], dict) else {}
    lines: list[str] = []
    lines.append(pal.bold("Semantic expression state"))
    lines.append(f"gateway: {snapshot.expression_probe_url or _gateway_base_url()}")
    if snapshot.expression_probe_error and not st:
        lines.append(pal.yellow("probe: " + crop(snapshot.expression_probe_error, max(10, width - 8))))
        lines.append("Expression module is not mounted or gateway is still starting.")
        lines.append("")
    else:
        lines.append("probe: " + (pal.green("ok") if not snapshot.expression_probe_error else pal.yellow(snapshot.expression_probe_error)))
    lines.append("")
    lines.append(pal.bold("Current state"))
    render_kv(lines, "emotion", st.get("emotion"), width)
    render_kv(lines, "arousal", st.get("arousal"), width)
    render_kv(lines, "attention", st.get("attention"), width)
    render_kv(lines, "energy", st.get("energy"), width)
    render_kv(lines, "speaking", st.get("speaking"), width)
    render_kv(lines, "listening", st.get("listening"), width)
    render_kv(lines, "confidence", st.get("confidence"), width)
    render_kv(lines, "source", st.get("source"), width)
    render_kv(lines, "reason", st.get("reason"), width)
    lines.append("")
    lines.append(pal.bold("Derived hardware targets"))
    led = targets.get("led") if isinstance(targets.get("led"), dict) else {}
    oled = targets.get("oled") if isinstance(targets.get("oled"), dict) else {}
    pose = targets.get("pose") if isinstance(targets.get("pose"), dict) else {}
    speech = targets.get("speech") if isinstance(targets.get("speech"), dict) else {}
    render_kv(lines, "led", f"{led.get('mode', '-')} {led.get('color', '-')}", width)
    render_kv(lines, "oled", f"{oled.get('mood', '-')} attention={oled.get('attention', '-')}", width)
    render_kv(lines, "pose", f"ear={pose.get('ear_gesture', '-')} energy={pose.get('energy', '-')}", width)
    render_kv(lines, "speech", f"tone={speech.get('tone', '-')} arousal={speech.get('arousal', '-')}", width)
    output_plan = getattr(snapshot, "expression_output_plan", {}) or {}
    output_status = getattr(snapshot, "expression_output_status", {}) or {}
    output_err = getattr(snapshot, "expression_output_probe_error", "") or ""
    if isinstance(output_plan, dict) or isinstance(output_status, dict):
        lines.append("")
        lines.append(pal.bold("Expression output bridge"))
        if output_err and not output_plan:
            lines.append(pal.yellow("probe: " + crop(output_err, max(10, width - 8))))
        else:
            lines.append("probe: " + (pal.green("ok") if not output_err else pal.yellow(output_err)))
        enabled = output_plan.get("enabled", output_status.get("enabled", "-")) if isinstance(output_plan, dict) else "-"
        dry = output_plan.get("dry_run_default", output_status.get("dry_run_default", "-")) if isinstance(output_plan, dict) else "-"
        render_kv(lines, "enabled/dry", f"{enabled}/{dry}", width)
        render_kv(lines, "actions", output_plan.get("action_count", "-") if isinstance(output_plan, dict) else "-", width)
        actions = output_plan.get("actions", []) if isinstance(output_plan, dict) else []
        if isinstance(actions, list) and actions:
            for action in actions[:3]:
                if not isinstance(action, dict):
                    continue
                comp = str(action.get("component") or "-")
                url = str(action.get("url") or "-")
                note = str(action.get("note") or "")
                lines.append(" " + crop(f"{comp:<10} {url} {note}", max(10, width - 2)))
        last_apply = output_status.get("last_apply") if isinstance(output_status, dict) else None
        if isinstance(last_apply, dict):
            render_kv(lines, "last_apply", f"applied={last_apply.get('applied')} reason={last_apply.get('reason', '-')}", width)
    if isinstance(event_counts, dict) and event_counts:
        lines.append("")
        lines.append(pal.bold("Top expression events"))
        for key, val in sorted(event_counts.items(), key=lambda kv: str(kv[1]), reverse=True)[:5]:
            lines.append(f" {crop(str(key), 28):<28} {val}")
    lines.append("")
    lines.append(pal.bold("History"))
    if not history:
        lines.append(" no expression state transitions yet")
    else:
        for rec in list(history)[-max(1, min(8, height - len(lines) - 1)):][::-1]:
            if not isinstance(rec, dict):
                continue
            nxt = rec.get("next") if isinstance(rec.get("next"), dict) else {}
            at = str(rec.get("at") or nxt.get("updated_at") or "-")
            at = at[11:19] if len(at) >= 19 else at
            msg = f"{nxt.get('emotion','-')} / {nxt.get('attention','-')} / {nxt.get('reason','-')}"
            lines.append(f" {at} {crop(msg, max(10, width - 12))}")
    return lines[:height]



def _json_post(path: str, payload: dict[str, Any] | None = None, timeout: float = 0.6) -> tuple[dict[str, Any] | None, str]:
    url = _gateway_base_url() + path
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local diagnostics only
            raw = resp.read(256_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return data if isinstance(data, dict) else {"value": data}, ""
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read(128_000).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                return data, f"HTTP {exc.code}"
        except Exception:
            pass
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, exc.__class__.__name__ + ": " + str(exc)

def refresh_companion_snapshot(snapshot: Snapshot, force: bool = False) -> None:
    now = time.monotonic()
    last = float(getattr(snapshot, "companion_last_probe", 0.0) or 0.0)
    if not force and (now - last) < 1.8:
        return
    snapshot.companion_last_probe = now
    snapshot.companion_probe_url = _gateway_base_url()
    needs, err = _json_get("/autonomy/needs", timeout=0.45)
    if needs is not None:
        snapshot.companion_needs = needs
        snapshot.companion_probe_error = ""
    else:
        snapshot.companion_probe_error = err
    goal, err2 = _json_get("/autonomy/goal", timeout=0.45)
    if goal is not None:
        snapshot.companion_goal = goal
        if not snapshot.companion_probe_error:
            snapshot.companion_probe_error = ""
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err2
    execution, err3 = _json_get("/autonomy/goal/execution", timeout=0.45)
    if execution is not None:
        snapshot.companion_execution = execution
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err3
    auto, err4 = _json_get("/autonomy/goal/auto", timeout=0.45)
    if auto is not None:
        snapshot.companion_auto = auto
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err4
    loop, err5 = _json_get("/autonomy/behavior-loop", timeout=0.45)
    if loop is not None:
        snapshot.companion_behavior_loop = loop
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err5
    memory, err6 = _json_get("/autonomy/memory", timeout=0.45)
    if memory is not None:
        snapshot.world_memory = memory
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err6
    autowrite, err7 = _json_get("/autonomy/memory/autowrite", timeout=0.45)
    if autowrite is not None:
        snapshot.world_memory_autowrite = autowrite
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err7
    shadow, err8 = _json_get("/autonomy/memory/decision-shadow", timeout=0.45)
    if shadow is not None:
        snapshot.memory_shadow = shadow
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err8
    bias, err9 = _json_get("/autonomy/memory/needs-bias", timeout=0.45)
    if bias is not None:
        snapshot.memory_needs_bias = bias
    elif not snapshot.companion_probe_error:
        snapshot.companion_probe_error = err9


def execute_companion_goal_dry_run(snapshot: Snapshot) -> None:
    result, err = _json_post("/autonomy/goal/execute?dry_run=true", {}, timeout=0.8)
    snapshot.companion_probe_url = _gateway_base_url()
    if result is not None:
        snapshot.companion_execution = result
        snapshot.companion_probe_error = ""
        needs, _err = _json_get("/autonomy/needs", timeout=0.35)
        if needs is not None:
            snapshot.companion_needs = needs
        goal, _err2 = _json_get("/autonomy/goal", timeout=0.35)
        if goal is not None:
            snapshot.companion_goal = goal
        auto, _err3 = _json_get("/autonomy/goal/auto", timeout=0.35)
        if auto is not None:
            snapshot.companion_auto = auto
    else:
        snapshot.companion_probe_error = err



def tick_companion_behavior_loop_dry_run(snapshot: Snapshot) -> None:
    result, err = _json_post("/autonomy/behavior-loop/tick?force=true&dry_run=true", {}, timeout=0.95)
    snapshot.companion_probe_url = _gateway_base_url()
    if result is not None:
        snapshot.companion_behavior_loop = result
        execution = result.get("execution") if isinstance(result.get("execution"), dict) else None
        if execution is not None:
            nested_execution = execution.get("execution") if isinstance(execution.get("execution"), dict) else execution
            if isinstance(nested_execution, dict):
                snapshot.companion_execution = nested_execution
            auto = dict(execution)
            auto.pop("execution", None)
            snapshot.companion_auto = auto
        snapshot.companion_probe_error = ""
        needs, _err = _json_get("/autonomy/needs", timeout=0.35)
        if needs is not None:
            snapshot.companion_needs = needs
        goal, _err2 = _json_get("/autonomy/goal", timeout=0.35)
        if goal is not None:
            snapshot.companion_goal = goal
    else:
        snapshot.companion_probe_error = err

def tick_companion_auto_dry_run(snapshot: Snapshot) -> None:
    result, err = _json_post("/autonomy/goal/auto/tick?force=true&dry_run=true", {}, timeout=0.9)
    snapshot.companion_probe_url = _gateway_base_url()
    if result is not None:
        snapshot.companion_auto = result
        execution = result.get("execution") if isinstance(result.get("execution"), dict) else None
        if execution is not None:
            snapshot.companion_execution = execution
        snapshot.companion_probe_error = ""
        needs, _err = _json_get("/autonomy/needs", timeout=0.35)
        if needs is not None:
            snapshot.companion_needs = needs
        goal, _err2 = _json_get("/autonomy/goal", timeout=0.35)
        if goal is not None:
            snapshot.companion_goal = goal
    else:
        snapshot.companion_probe_error = err

def _score_bar(value: object, width: int = 18) -> str:
    try:
        val = max(0.0, min(100.0, float(value)))
    except Exception:
        val = 0.0
    filled = int(round((val / 100.0) * width))
    return "#" * filled + "." * max(0, width - filled)


def render_companion(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    needs = getattr(snapshot, "companion_needs", {}) or {}
    goal = getattr(snapshot, "companion_goal", {}) or {}
    execution = getattr(snapshot, "companion_execution", {}) or {}
    auto = getattr(snapshot, "companion_auto", {}) or {}
    loop = getattr(snapshot, "companion_behavior_loop", {}) or {}
    scores = needs.get("scores") if isinstance(needs.get("scores"), dict) else goal.get("scores") if isinstance(goal.get("scores"), dict) else {}
    actions = goal.get("actions") if isinstance(goal.get("actions"), list) else []
    steps = execution.get("steps") if isinstance(execution.get("steps"), list) else []
    auto_decision = auto.get("last_decision") if isinstance(auto.get("last_decision"), dict) else auto
    loop_decision = loop.get("last_decision") if isinstance(loop.get("last_decision"), dict) else loop
    loop_history = loop.get("history") if isinstance(loop.get("history"), list) else []
    memory = getattr(snapshot, "world_memory", {}) or {}
    autowrite = getattr(snapshot, "world_memory_autowrite", {}) or {}
    mem_counts = memory.get("counts") if isinstance(memory.get("counts"), dict) else {}
    mem_recent = memory.get("recent") if isinstance(memory.get("recent"), list) else []
    aw_items = autowrite.get("items") if isinstance(autowrite.get("items"), list) else []
    memory_shadow = getattr(snapshot, "memory_shadow", {}) or {}
    memory_bias = getattr(snapshot, "memory_needs_bias", {}) or {}

    def yn(v: object) -> str:
        if isinstance(v, bool):
            return "Y" if v else "N"
        return str(v)

    def reason_line(d: dict, key: str = "reason") -> str:
        if not isinstance(d, dict):
            return "-"
        return crop(str(d.get(key, "-")), max(8, width - 38))

    lines: list[str] = []
    lines.append(pal.bold("Companion needs / goal / loop / execution"))
    probe = "ok" if not snapshot.companion_probe_error else crop(snapshot.companion_probe_error, max(10, width - 10))
    lines.append(f"probe={probe}  gateway={snapshot.companion_probe_url or _gateway_base_url()}")

    dominant = needs.get("dominant_need", goal.get("dominant_need", "-"))
    recommended = needs.get("recommended_goal", goal.get("recommended_goal", "-"))
    behavior = goal.get("behavior", recommended)
    priority = goal.get("priority", "-")
    idle_s = needs.get("idle_s", "-")
    owner_present = needs.get("owner_present", goal.get("owner_present", "-"))

    lines.append("")
    lines.append(pal.bold("Need / goal"))
    lines.append(f" need={crop(str(dominant), 14):<14} goal={crop(str(recommended), max(8, width - 30))}")
    lines.append(f" behavior={crop(str(behavior), max(8, width - 34))} prio={priority} idle={idle_s} owner={yn(owner_present)}")
    lines.append(f" safe={yn(goal.get('safe_to_execute', '-'))} auto={yn(goal.get('auto_execute', '-'))} expr={crop(str(goal.get('expression_event', '-')), max(8, width - 30))}")

    lines.append("")
    lines.append(pal.bold("Memory decision"))
    if memory_shadow:
        shadow_need = memory_shadow.get("recommended_need", "-")
        shadow_goal = memory_shadow.get("recommended_goal", "-")
        shadow_mode = memory_shadow.get("mode", "-")
        shadow_apply = memory_shadow.get("apply_to_needs", False)
        shadow_conf = memory_shadow.get("confidence", 0)
        try:
            shadow_conf_s = f"{float(shadow_conf):.2f}"
        except Exception:
            shadow_conf_s = str(shadow_conf)
        lines.append(f" shadow={shadow_need}/{crop(str(shadow_goal), max(8, width - 28))}")
        lines.append(f" mode={shadow_mode} apply={shadow_apply} conf={shadow_conf_s}")
    else:
        lines.append(" shadow=-")
    if memory_bias:
        bias_need = memory_bias.get("result_need") or memory_bias.get("memory_need") or "-"
        bias_goal = memory_bias.get("result_goal") or memory_bias.get("memory_goal") or "-"
        applied = memory_bias.get("applied", False)
        reason = memory_bias.get("reason", "-")
        boost = memory_bias.get("boost", "-")
        lines.append(f" bias={bias_need}/{crop(str(bias_goal), max(8, width - 26))}")
        lines.append(f" applied={applied} boost={boost} reason={crop(str(reason), max(8, width - 31))}")
    else:
        lines.append(" bias=-")

    lines.append(pal.bold("Behavior loop"))
    if loop:
        lines.append(f" enabled={yn(loop.get('enabled', '-'))} interval={loop.get('interval_s', '-')}s min_idle={loop.get('min_idle_s', '-')}s dry={yn(loop.get('dry_run', '-'))}")
        lines.append(f" decision={reason_line(loop_decision)} tick={yn(loop_decision.get('should_tick', '-'))} exec={yn(loop_decision.get('executed', '-'))}")
    else:
        lines.append(" no behavior loop probe yet; use r or :looptick")

    # Keep this near the top. Previous layout hid it on compact terminals.
    lines.append("")
    lines.append(pal.bold("Recent behavior loop"))
    if loop_history:
        max_hist = max(1, min(3, max(1, height - len(lines) - 12)))
        for idx, item in enumerate(loop_history[:max_hist], 1):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or item.get("execution_reason") or "-")
            plan = str(item.get("plan_id") or item.get("behavior") or "-")
            ex = yn(item.get("executed") if "executed" in item else item.get("available", "-"))
            lines.append(f" {idx:02d}. {crop(reason, 16):<16} exec={ex:<3} {crop(plan, max(8, width - 36))}")
    else:
        lines.append(" no history yet; use :looptick")

    lines.append("")
    lines.append(pal.bold("World memory"))
    if memory:
        try:
            total = int(memory.get("total", 0) or 0)
        except Exception:
            total = 0
        lines.append(f" total={total} people={mem_counts.get('people', 0)} objects={mem_counts.get('objects', 0)} events={mem_counts.get('events', 0)} obs={mem_counts.get('observations', 0)}")
        if mem_recent:
            item = mem_recent[0] if isinstance(mem_recent[0], dict) else {}
            label = f"{item.get('kind', '-')}/{item.get('name', '-')}"
            src = item.get("source", "-")
            cnt = item.get("count", "-")
            lines.append(f" latest={crop(str(label), max(8, width - 34))} src={src} x{cnt}")
        else:
            lines.append(" latest=-")
        if autowrite:
            aw_src = autowrite.get("source_type", "-")
            aw_count = autowrite.get("count", 0)
            aw_created = autowrite.get("created_count", 0)
            if aw_items:
                aw_item = aw_items[0] if isinstance(aw_items[0], dict) else {}
                aw_label = f"{aw_item.get('kind', '-')}/{aw_item.get('name', '-')}"
                lines.append(f" autowrite={aw_src} count={aw_count} created={aw_created} {crop(str(aw_label), max(8, width - 46))}")
            else:
                lines.append(f" autowrite={aw_src} count={aw_count} created={aw_created}")
    else:
        lines.append(" no world-memory probe yet; use r or :memory")

    lines.append(pal.bold("Auto-execute gate"))
    if auto:
        lines.append(f" enabled={yn(auto.get('enabled', '-'))} dry={yn(auto.get('dry_run_default', auto.get('dry_run', '-')))} real_hw={yn(auto.get('allow_real_hardware', '-'))}")
        lines.append(f" decision={reason_line(auto_decision)} run={yn(auto_decision.get('should_execute', '-'))} exec={yn(auto_decision.get('executed', '-'))}")
    else:
        lines.append(" no auto gate probe yet; use r")

    lines.append("")
    lines.append(pal.bold("Execution dry-run"))
    if execution:
        lines.append(f" enabled={yn(execution.get('enabled', '-'))} dry={yn(execution.get('dry_run', execution.get('dry_run_default', '-')))} applied={yn(execution.get('applied', '-'))}")
        lines.append(f" available={yn(execution.get('available', '-'))} reason={crop(str(execution.get('reason', '-')), max(8, width - 32))} steps={execution.get('step_count', len(steps))}")
        for idx, step in enumerate(steps[:2], 1):
            if not isinstance(step, dict):
                continue
            component = str(step.get("component") or "-")
            url = str(step.get("url") or "-")
            risk = str(step.get("risk") or "-")
            lines.append(f" {idx:02d}. {component:<10} {crop(url, max(8, width - 32))} risk={risk}")
    else:
        lines.append(" no execution probe yet; use :execute")

    if height - len(lines) > 5:
        lines.append("")
        lines.append(pal.bold("Safe action plan"))
        if actions:
            for idx, action in enumerate(actions[:2], 1):
                if not isinstance(action, dict):
                    continue
                typ = str(action.get("type") or "-")
                label = str(action.get("event") or action.get("name") or action.get("label") or action.get("mode") or "-")
                risk = str(action.get("risk") or "-")
                lines.append(f" {idx:02d}. {typ:<10} {crop(label, max(8, width - 30))} risk={risk}")
        else:
            lines.append(" no action plan yet")

    if height - len(lines) > 4:
        lines.append("")
        lines.append(pal.bold("Need scores"))
        if isinstance(scores, dict) and scores:
            order = ["social", "curiosity", "boredom", "energy", "rest", "safety", "owner_proximity", "exploration"]
            remaining = max(0, height - len(lines))
            for key in order[:remaining]:
                if key in scores:
                    try:
                        val = float(scores.get(key) or 0.0)
                        val_s = f"{val:5.1f}"
                    except Exception:
                        val_s = str(scores.get(key))
                    bar = _score_bar(scores.get(key), width=max(6, min(16, width - 24)))
                    lines.append(f" {key:<16} {val_s:>6} {bar}")
        else:
            lines.append(" no scores yet")
    return lines[:height]

def render_overview(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool) -> list[str]:
    lines: list[str] = []
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    mode = "PC TEST MODE" if ui.profile == "pc-test" else "ROBOT MODE"
    lines.append(f"{pal.yellow(mode) if ui.profile == 'pc-test' else pal.green(mode)}  services OK:{oks} PC:{pc_count} WARN:{warns} ERR:{errs}  uptime:{snapshot.uptime}")
    lines.append(pal.dim("Hardware-missing warnings are grouped separately during PC tests."))
    lines.append("")

    names = ["CORE", "AI", "VISION", "AUDIO", "TTS", "MOVE"]
    card_w = max(18, (width - 4) // 3)
    cards = [service_card(snapshot.services.get(n, ServiceStatus(n)), card_w, pal) for n in names]
    lines.append(pal.bold("Runtime map"))
    for row in range(0, len(cards), 3):
        group = cards[row:row+3]
        for sub in range(2):
            lines.append("  ".join(fit(card[sub], card_w) for card in group))
        lines.append("")

    blockers = list(snapshot.blockers.values())[-12:]
    expected = [(c, d, t) for c, d, t in blockers if ui.profile == "pc-test" and is_pc_expected(d)]
    real = [(c, d, t) for c, d, t in blockers if not (ui.profile == "pc-test" and is_pc_expected(d))]

    lines.append(pal.bold("Needs attention"))
    if real:
        for chan, desc, t in real[-5:]:
            lines.append(f" {pal.dim(t)} {pal.level('WARN'):<9} {chan:<7} {desc}")
    else:
        lines.append(" no non-PC blockers detected")
    lines.append("")
    lines.append(pal.bold("Expected missing on PC"))
    if expected:
        for chan, desc, t in expected[-5:]:
            lines.append(f" {pal.dim(t)} {chan:<7} {desc}")
    else:
        lines.append(" none detected")

    lines.append("")
    lines.append(pal.bold("Signal pressure"))
    top = snapshot.endpoints.most_common(5)
    max_count = top[0][1] if top else 1
    if top:
        for ep, count in top:
            kind = "poll" if ep in {"/vlm/context/latest", "/vlm/results/latest", "/state/get", "/speech/last", "/speech/direction", "/arduino/request"} else "action"
            lines.append(f" {ep:<30} {kind:<6} {hbar(count, max_count, 14, pal)} {count}")
    else:
        lines.append(" waiting for endpoint activity")
    return lines[:height]


def render_logs(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    events = newest_first_events(snapshot, ui)
    if events:
        ui.selected_event = min(max(0, ui.selected_event), len(events) - 1)
    header = (
        f"view:{ui.log_view}  filter:{ui.filter_text or '<none>'}  "
        f"events:{len(events)}  selected:{ui.selected_event+1 if events else 0}  hidden-noise:{snapshot.hidden_noise}"
    )
    lines = [pal.dim(header), pal.dim("Newest first. Up/Down selects, v cycles human/full/warn, / filters."), ""]
    usable = max(0, height - 3)
    start = min(max(0, ui.scroll), max(0, len(events) - 1))
    visible = events[start:start + usable]
    for row, ev in enumerate(visible, start):
        prefix = "> " if row == ui.selected_event else "  "
        line = event_line(ev, max(1, width - 2), pal)
        lines.append(prefix + line[: max(1, width - 2)])
    if not visible:
        lines.append("  no events match current view/filter")
    return lines[:height]

def render_signals(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines: list[str] = []
    lines.append(pal.bold("Polls vs real work"))
    lines.append("/vlm/context/latest and /vlm/results/latest are cache/result polls, not necessarily expensive VLM inference.")
    lines.append("/arduino/request is command/bridge traffic; on PC tests it may be synthetic or degraded.")
    lines.append("")
    top = snapshot.endpoints.most_common(14)
    max_count = top[0][1] if top else 1
    lines.append(pal.bold("HTTP endpoints"))
    for ep, count in top:
        kind = "poll" if ep in {"/vlm/context/latest", "/vlm/results/latest", "/state/get", "/speech/last", "/speech/direction", "/arduino/request"} else "action"
        lines.append(f" {ep:<34} {kind:<6} {hbar(count, max_count, 18, pal)} {count}")
    lines.append("")
    lines.append(pal.bold("Remote hosts"))
    if snapshot.remote_hosts:
        for host, count in snapshot.remote_hosts.most_common(8):
            lines.append(f" {host:<22} {hbar(count, max(snapshot.remote_hosts.values()), 18, pal)} {count}")
    else:
        lines.append(" no remote host activity detected")
    return lines[:height]


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


def render_config(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    files = list_config_files(ui.root)
    left_w = min(38, max(24, width // 3))
    right_w = width - left_w - 3
    selected = min(max(0, ui.selected_config), max(0, len(files) - 1))
    ui.selected_config = selected
    left: list[str] = [pal.dim("YAML files  (Up/Down select, e edit)")]
    for idx, path in enumerate(files[: max(1, height - 2)]):
        rel = str(path.relative_to(ui.root)).replace("\\", "/")
        line = f"{idx+1:>2} {rel}"
        left.append(pal.cyan(line) if idx == selected else line)
    if not files:
        left.append("no yaml config files found")
    right: list[str] = []
    if files:
        rel = str(files[selected].relative_to(ui.root)).replace("\\", "/")
        right.append(pal.bold(rel))
        right.append(pal.dim("edit: press e, enter dotted.key, enter value"))
        right.append("")
        for i, line in enumerate(preview_file(files[selected], max(0, height - 4)), 1):
            right.append(f"{i:>3} {line}")
    rows = []
    for i in range(height):
        l = fit(left[i] if i < len(left) else "", left_w)
        r = fit(right[i] if i < len(right) else "", right_w)
        rows.append(l + pal.dim(" | ") + r)
    return rows


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


def render_search(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [pal.dim(f"query: {ui.project_search or '<none>'}  results:{len(ui.project_results)}  press s to search")]
    lines.append("")
    for res in ui.project_results[: max(0, height - 2)]:
        lines.append(f"{pal.cyan(res.path)}:{res.line}  {res.text}")
    if not ui.project_results and not ui.project_search:
        lines.append("Try: s  piper / vosk / vlm / auth_token / arduino")
    return lines[:height]


def render_actions(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Command workspace"),
        "This screen is intentionally safe for PC testing; it does not assume robot hardware is attached.",
        "",
        pal.bold("Command palette"),
        " :profile pc              classify hardware warnings as expected PC-test gaps",
        " :profile robot           classify hardware warnings as real robot blockers",
        " :filter <text>           filter Logs tab",
        " :view human|full|warn    change Logs view mode",
        " :search <text>           project-wide search",
        " :set <key> <value>       edit selected YAML key from Config tab",
        " :camera refresh          probe /camera/status now",
        " :expression refresh      probe /expression/state now",
        " :expression output       view dry-run output plan",
        " :tab camera             open Camera / IMX500 panel",
        " :quit                    exit TUI",
        "",
        pal.bold("Next engineering phases"),
        " 08 vision request gate: stop unnecessary VLM calls and label true inference vs polls",
        " 09 persistent TTS worker: load Piper once and prevent test-tone-success speech",
        " 10 semantic expression engine: one source for LED/OLED/emotion/motion state",
    ]
    return lines[:height]


def render_help(width: int, height: int, pal: Palette) -> list[str]:
    lines = [
        pal.bold("Navigation"),
        " 1-9             switch workspace tab",
        " Up/Down         move log selection or config file selection",
        " PageUp/PageDn   scroll log viewport",
        " /               filter logs",
        " v               cycle log view: human/full/warn",
        " s               search project files",
        " e               edit selected YAML key in Config",
        " :               command palette",
        " c               clear filter/search/message",
        " r               refresh immediately",
        " q               quit",
        "",
        pal.bold("Layout"),
        " Navigator: sections and health",
        " Workspace: selected tool view",
        " Inspector: selected log/config/event details and suggested fix",
        " Command bar: input and active shortcut state",
        "",
        pal.bold("Logs"),
        " Raw stdout: logs/runtime_stdout.log",
        " Detailed runtime log: logs/sentry.log",
        " TUI hides polling spam from Overview and groups it in Signals.",
        " Camera tab: live /camera/status and /camera/onsensor/latest diagnostics",
        " Expression tab: live semantic state, targets, event history",
        " Companion tab: needs + semantic goal selector",
        " :execute dry-run current companion goal",
        " :autotick dry-run auto gate tick",
        " :looptick dry-run behavior loop tick",
        " :memory refresh world-memory panel",
        " :memorybias refresh memory shadow/bias",
    ]
    return lines[:height]


def render_main(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool) -> list[str]:
    tab_name = TABS[ui.active_tab] if 0 <= ui.active_tab < len(TABS) else "Overview"
    inner_h = height - 2
    if tab_name == "Overview":
        content = render_overview(width, inner_h, snapshot, ui, pal, ascii_mode)
    elif tab_name == "Logs":
        content = render_logs(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Signals":
        content = render_signals(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Config":
        content = render_config(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Search":
        content = render_search(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Actions":
        content = render_actions(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Companion":
        content = render_companion(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Expression":
        content = render_expression(width, inner_h, snapshot, ui, pal)
    elif tab_name == "Camera":
        content = render_camera(width, inner_h, snapshot, ui, pal)
    else:
        content = render_help(width, inner_h, pal)
    return box("WORKSPACE / " + tab_name.upper(), [tab_strip(width - 4, ui, pal), ""] + content, width, height, pal, ascii_mode)


def render_right(width: int, height: int, snapshot: Snapshot, ui: UIState, pal: Palette, ascii_mode: bool) -> list[str]:
    lines: list[str] = []
    errs, warns, oks, pc_count = health_summary_for(snapshot, ui)
    ev = selected_event(snapshot, ui)
    lines.append(pal.bold("Runtime"))
    lines.append(f"profile      {'PC TEST' if ui.profile == 'pc-test' else 'ROBOT'}")
    lines.append(f"health       {pal.red(str(errs)+' err') if errs else pal.green('no err')}  {pal.cyan(str(pc_count)+' pc') if pc_count else pal.green('no pc')}  {pal.yellow(str(warns)+' warn') if warns else pal.green('no warn')}")
    lines.append(f"events       {len(snapshot.events)}")
    lines.append(f"hidden noise {snapshot.hidden_noise}")
    lines.append("")
    lines.append(pal.bold("Selected event"))
    if ev is not None:
        lines.append(f"time         {ev.time}")
        lines.append(f"level        {ev.level.upper().replace('WARNING','WARN')}")
        lines.append(f"channel      {ev.channel}")
        lines.append(f"source       {crop(ev.source, max(8, width - 14))}")
        lines.append("message")
        msg = clean_path(ev.message)
        chunk = max(12, width - 4)
        for i in range(0, min(len(msg), chunk * 5), chunk):
            lines.append("  " + crop(msg[i:i+chunk], chunk))
    else:
        lines.append("no event selected")
    lines.append("")
    lines.append(pal.bold("Suggested fix"))
    for item in suggested_fix(ev, ui)[:7]:
        lines.append("- " + crop(item, max(8, width - 4)))
    lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Companion":
        lines.append(pal.bold("Companion quick view"))
        goal = getattr(snapshot, "companion_goal", {}) or {}
        needs = getattr(snapshot, "companion_needs", {}) or {}
        lines.append(f"need        {crop(str(needs.get('dominant_need', goal.get('dominant_need', '-'))), max(8, width - 14))}")
        lines.append(f"goal        {crop(str(goal.get('behavior', needs.get('recommended_goal', '-'))), max(8, width - 14))}")
        lines.append(f"priority    {crop(str(goal.get('priority', '-')), max(8, width - 14))}")
        lines.append(f"actions     {len(goal.get('actions') or [])}")
        execution = getattr(snapshot, "companion_execution", {}) or {}
        lines.append(f"execution   {crop(str(execution.get('reason', '-')), max(8, width - 14))}")
        auto = getattr(snapshot, "companion_auto", {}) or {}
        decision = auto.get("last_decision") if isinstance(auto.get("last_decision"), dict) else auto
        lines.append(f"auto_gate   {crop(str(decision.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe       {crop(snapshot.companion_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Expression":
        lines.append(pal.bold("Expression quick view"))
        core = _expression_core(snapshot)
        st = core["state"]
        lines.append(f"emotion     {crop(str(st.get('emotion', '-')), max(8, width - 14))}")
        lines.append(f"attention   {crop(str(st.get('attention', '-')), max(8, width - 14))}")
        lines.append(f"arousal     {crop(str(st.get('arousal', '-')), max(8, width - 14))}")
        lines.append(f"reason      {crop(str(st.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe       {crop(snapshot.expression_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
        output_plan = getattr(snapshot, "expression_output_plan", {}) or {}
        if isinstance(output_plan, dict) and output_plan:
            lines.append(pal.bold("Output quick view"))
            lines.append(f"enabled     {output_plan.get('enabled', '-')}")
            lines.append(f"dry_run     {output_plan.get('dry_run_default', '-')}")
            lines.append(f"actions     {output_plan.get('action_count', '-')}")
            lines.append("")
    if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Camera":
        lines.append(pal.bold("Camera quick view"))
        status = snapshot.camera_status or {}
        cap = status.get("capture") if isinstance(status.get("capture"), dict) else {}
        imx = status.get("imx500") if isinstance(status.get("imx500"), dict) else {}
        lines.append(f"camera       {'live' if status.get('live') else 'not live'}")
        lines.append(f"backend      {crop(str(cap.get('backend', '-')), max(8, width - 14))}")
        lines.append(f"imx500       {crop(str(imx.get('reason', '-')), max(8, width - 14))}")
        lines.append(f"probe        {crop(snapshot.camera_probe_error or 'ok', max(8, width - 14))}")
        lines.append("")
    lines.append(pal.bold("Top endpoints"))
    for ep, count in snapshot.endpoints.most_common(4):
        lines.append(f"{crop(ep, max(8, width - 8)):<{max(8, width - 8)}} {count}")
    return box("INSPECTOR", lines, width, height, pal, ascii_mode)


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


def render_screen(snapshot: Snapshot, ui: UIState, robot_status: str, colors: bool = True, ascii_mode: bool = False) -> str:
    pal = Palette(colors)
    size = shutil.get_terminal_size((132, 38))
    width = max(96, size.columns)
    height = max(26, size.lines)
    header_h = 2
    footer_h = 3
    body_h = height - header_h - footer_h
    side_w = 26
    right_w = 38 if width >= 126 else 0
    gap = 1
    main_w = width - side_w - right_w - (gap * (2 if right_w else 1))
    out: list[str] = [draw_header(width, snapshot, ui, robot_status, pal)]
    breadcrumb = f" workspace={TABS[ui.active_tab].lower()}  root={crop(str(ui.root), max(10, width - 50))}"
    out.append(fit(pal.dim(breadcrumb), width))
    side = draw_sidebar(body_h, side_w, ui, snapshot, pal, ascii_mode)
    main = render_main(main_w, body_h, snapshot, ui, pal, ascii_mode)
    right = render_right(right_w, body_h, snapshot, ui, pal, ascii_mode) if right_w else []
    for i in range(body_h):
        line = side[i] + " " + main[i]
        if right_w:
            line += " " + right[i]
        out.append(fit(line, width))
    prompt = command_prompt(ui)
    status = f" tab={TABS[ui.active_tab]}  view={ui.log_view}  filter={ui.filter_text or '-'}  selected={ui.selected_event + 1} "
    out.append(fit("-" * width, width))
    out.append(fit(status, width))
    out.append(fit(prompt, width))
    return safe_text("\n".join(out))


def handle_command(ui: UIState, snapshot: Snapshot, text: str) -> None:
    text = text.strip()
    if not text:
        return
    parts = text.split()
    cmd = parts[0].lower()
    arg = text[len(parts[0]):].strip() if parts else ""
    if cmd in {"q", "quit", "exit"}:
        ui.message = "quit requested"
        raise KeyboardInterrupt
    if cmd == "profile" and arg.lower() in {"pc", "pc-test", "test"}:
        ui.profile = "pc-test"
        ui.message = "profile set to PC TEST"
    elif cmd == "profile" and arg.lower() in {"robot", "rpi", "pi"}:
        ui.profile = "robot"
        ui.message = "profile set to ROBOT"
    elif cmd in {"filter", "f"}:
        ui.filter_text = arg
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"filter set: {arg}"
    elif cmd == "view" and arg.lower() in {"human", "full", "warn"}:
        ui.log_view = arg.lower()
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"log view set: {ui.log_view}"
    elif cmd in {"search", "s"}:
        ui.project_search = arg
        ui.project_results = project_search(ui.root, arg)
        ui.active_tab = 4
        ui.message = f"search complete: {len(ui.project_results)} results"
    elif cmd == "camera" and arg.lower() in {"refresh", "status", "probe"}:
        refresh_camera_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Camera") if "Camera" in TABS else ui.active_tab
        ui.message = "camera status refreshed"
    elif cmd in {"memorybias", "bias", "shadow"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "memory shadow/bias refreshed"
    elif cmd in {"memory", "mem", "worldmemory"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "world memory refreshed"
    elif cmd in {"looptick", "loop", "behaviorloop"}:
        tick_companion_behavior_loop_dry_run(snapshot)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion behavior loop dry-run tick executed"
    elif cmd in {"autotick", "autoexecute", "autogoal"}:
        tick_companion_auto_dry_run(snapshot)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion auto gate dry-run tick executed"
    elif cmd in {"execute", "dryrun", "goalrun"}:
        execute_companion_goal_dry_run(snapshot)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion goal dry-run executed"
    elif cmd in {"companion", "goal", "needs"}:
        refresh_companion_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Companion") if "Companion" in TABS else ui.active_tab
        ui.message = "companion goal refreshed"
    elif cmd == "expression" and (arg.lower() in {"refresh", "status", "state", "probe"} or not arg):
        refresh_expression_snapshot(snapshot, force=True)
        refresh_expression_output_snapshot(snapshot, force=True)
        ui.active_tab = TABS.index("Expression") if "Expression" in TABS else ui.active_tab
        ui.message = "expression state refreshed"
    elif cmd == "tab" and arg:
        for idx, name in enumerate(TABS):
            if name.lower().startswith(arg.lower()):
                ui.active_tab = idx
                return
        ui.message = f"unknown tab: {arg}"
    elif cmd == "set" and len(parts) >= 3:
        key = parts[1]
        value = text.split(None, 2)[2]
        ui.message = edit_yaml(ui.root, ui.selected_config, key, value)
    else:
        ui.message = f"unknown command: {cmd}"


def handle_key(key: str | None, ui: UIState, snapshot: Snapshot) -> None:
    if key is None:
        return
    if ui.command_mode:
        if key == "ESC":
            ui.command_mode = ""
            ui.command_buffer = ""
            ui.pending_key = ""
            return
        if key == "BACKSPACE":
            ui.command_buffer = ui.command_buffer[:-1]
            return
        if key == "ENTER":
            buf = ui.command_buffer
            mode = ui.command_mode
            ui.command_buffer = ""
            ui.command_mode = ""
            if mode == "filter":
                ui.filter_text = buf.strip()
                ui.active_tab = 1
                ui.selected_event = 0
                ui.scroll = 0
                ui.message = f"filter set: {ui.filter_text or '<none>'}"
            elif mode == "project_search":
                ui.project_search = buf.strip()
                ui.project_results = project_search(ui.root, ui.project_search)
                ui.active_tab = 4
                ui.message = f"search complete: {len(ui.project_results)} results"
            elif mode == "command":
                handle_command(ui, snapshot, buf)
            elif mode == "edit_key":
                ui.pending_key = buf.strip()
                ui.command_mode = "edit_value"
            elif mode == "edit_value":
                ui.message = edit_yaml(ui.root, ui.selected_config, ui.pending_key, buf)
                ui.pending_key = ""
            return
        if len(key) == 1 and key.isprintable():
            ui.command_buffer += key
        return

    if key in {"q", "Q"}:
        raise KeyboardInterrupt
    if key.isdigit() and 1 <= int(key) <= len(TABS):
        ui.active_tab = int(key) - 1
        ui.scroll = 0
        if ui.active_tab == 1:
            ui.selected_event = 0
    elif key in {"v", "V"}:
        order = ["human", "full", "warn"]
        ui.log_view = order[(order.index(ui.log_view) + 1) % len(order)] if ui.log_view in order else "human"
        ui.active_tab = 1
        ui.selected_event = 0
        ui.scroll = 0
        ui.message = f"log view: {ui.log_view}"
    elif key == "/":
        ui.command_mode = "filter"
        ui.command_buffer = ui.filter_text
    elif key in {"s", "S"}:
        ui.command_mode = "project_search"
        ui.command_buffer = ui.project_search
    elif key == ":":
        ui.command_mode = "command"
    elif key in {"e", "E"}:
        if ui.active_tab == 3:
            ui.command_mode = "edit_key"
            ui.command_buffer = ""
        else:
            ui.message = "edit is available on Config tab"
    elif key in {"c", "C"}:
        ui.filter_text = ""
        ui.project_search = ""
        ui.project_results = []
        ui.message = "cleared"
    elif key in {"r", "R"}:
        if 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Companion":
            refresh_companion_snapshot(snapshot, force=True)
            ui.message = "companion goal refreshed"
        elif 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Camera":
            refresh_camera_snapshot(snapshot, force=True)
            ui.message = "camera status refreshed"
        elif 0 <= ui.active_tab < len(TABS) and TABS[ui.active_tab] == "Expression":
            refresh_expression_snapshot(snapshot, force=True)
            refresh_expression_output_snapshot(snapshot, force=True)
            ui.message = "expression state/output refreshed"
        else:
            ui.message = "refreshed"
    elif key == "UP":
        if ui.active_tab == 3:
            ui.selected_config = max(0, ui.selected_config - 1)
        elif ui.active_tab == 1:
            ui.selected_event = max(0, ui.selected_event - 1)
            ui.scroll = max(0, min(ui.scroll, ui.selected_event))
        else:
            ui.scroll += 1
    elif key == "DOWN":
        if ui.active_tab == 3:
            ui.selected_config += 1
        elif ui.active_tab == 1:
            ui.selected_event += 1
            ui.scroll = max(ui.scroll, ui.selected_event - 2)
        else:
            ui.scroll = max(0, ui.scroll - 1)
    elif key == "PGUP":
        if ui.active_tab == 1:
            ui.selected_event = max(0, ui.selected_event - 10)
            ui.scroll = max(0, min(ui.scroll, ui.selected_event))
        else:
            ui.scroll += 10
    elif key == "PGDN":
        if ui.active_tab == 1:
            ui.selected_event += 10
            ui.scroll = max(ui.scroll, ui.selected_event - 2)
        else:
            ui.scroll = max(0, ui.scroll - 10)


def run_tui(root: Path, run_robot: bool, colors: bool, ascii_mode: bool, no_alt: bool, profile: str | None = None) -> int:
    force_utf8_stdio()
    enable_virtual_terminal()
    # Safe ASCII is the default on Windows/CMD and remains harmless elsewhere.
    ascii_mode = True if os.environ.get("SENTRYBOT_TUI_UNICODE", "0") != "1" else ascii_mode
    root = root.resolve()
    snapshot = Snapshot()
    detected_profile = "pc-test" if is_pc_test(root) else "robot"
    ui = UIState(root=root, profile=profile or detected_profile)
    tailer = LogTailer(root, start_at_end=run_robot)
    robot = RobotProcess(root, enabled=run_robot, profile=ui.profile)
    ui.message = robot.start()
    alt_on = sys.stdout.isatty() and (not no_alt)
    restored = False

    def restore_terminal() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        try:
            sys.stdout.write("\x1b[?25h")
            if alt_on:
                sys.stdout.write("\x1b[?1049l")
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass

    atexit.register(restore_terminal)
    try:
        if alt_on:
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            sys.stdout.flush()
        with KeyReader() as keys:
            while True:
                if not ui.paused:
                    tailer.read_new(snapshot)
                    refresh_camera_snapshot(snapshot)
                    refresh_expression_snapshot(snapshot)
                    refresh_expression_output_snapshot(snapshot)
                    refresh_companion_snapshot(snapshot)
                key = keys.read()
                handle_key(key, ui, snapshot)
                screen = render_screen(snapshot, ui, robot.status, colors=colors, ascii_mode=ascii_mode)
                if alt_on:
                    sys.stdout.write("\x1b[H" + screen)
                else:
                    sys.stdout.write("\x1b[2J\x1b[H" + screen)
                sys.stdout.flush()
                time.sleep(DEFAULT_REFRESH)
    except KeyboardInterrupt:
        ui.message = "stopping"
        return 0
    finally:
        try:
            robot.stop()
        except Exception:
            pass
        restore_terminal()
        try:
            atexit.unregister(restore_terminal)
        except Exception:
            pass

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT opencode-style terminal UI")
    parser.add_argument("--root", default=os.getcwd(), help="SentryBOT project root")
    parser.add_argument("--run", action="store_true", help="start run_robot.py as a subprocess")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--ascii", action="store_true", help="use ASCII borders")
    parser.add_argument("--unicode", action="store_true", help="allow Unicode borders (not recommended on Windows CMD)")
    parser.add_argument("--no-alt", action="store_true", help="do not use terminal alternate screen")
    parser.add_argument("--alt", action="store_true", help="use terminal alternate screen")
    parser.add_argument("--profile", choices=["pc", "pc-test", "robot"], default=None, help="override detected runtime profile")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not (root / "scripts" / "run_robot.py").exists():
        print(f"run_robot.py not found under {root / 'scripts'}", file=sys.stderr)
        return 2
    profile = "pc-test" if args.profile == "pc" else args.profile
    if args.unicode:
        os.environ["SENTRYBOT_TUI_UNICODE"] = "1"
    no_alt = True
    if args.alt:
        no_alt = False
    if args.no_alt:
        no_alt = True
    return run_tui(root=root, run_robot=args.run, colors=not args.no_color, ascii_mode=(args.ascii or not args.unicode), no_alt=no_alt, profile=profile)


if __name__ == "__main__":
    raise SystemExit(main())
