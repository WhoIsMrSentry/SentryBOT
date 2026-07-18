from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

APP_TITLE = "SENTRYBOT CONTROL CENTER"
_REFRESH_S = 0.35
_MAX_FILE_BYTES = 700_000
_SEARCH_EXTS = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".log", ".ini", ".toml"}

NOISE_PATTERNS = (
    "SECURITY WARNING:",
    "module ",
    "bridge mounted",
    "wired to interactions engine",
    "Started server process",
    "Waiting for application startup",
    "Application startup complete",
    "Press Ctrl+C",
    "Loaded gateway config",
    "Available modules:",
)

STATUS_RULES = {
    "AI": (
        ("api_key is missing", "ERR", "Google API key missing"),
        ("LLM chat failed", "ERR", "LLM endpoint failed"),
        ("Provider client init failed", "ERR", "Provider init failed"),
        ("Agent Core running", "OK", "Agent started"),
    ),
    "TTS": (
        ("piper unavailable", "WARN", "Piper model missing"),
        ("dummy", "WARN", "Dummy voice fallback"),
        ("First audio", "OK", "Audio started"),
    ),
    "AUDIO": (
        ("Vosk TR model missing", "ERR", "TR Vosk model missing"),
        ("Vosk model directory not found", "ERR", "Vosk model missing"),
        ("wakeword listening started", "OK", "Wakeword listening"),
        ("SpeechArbiter started", "OK", "Speech arbiter started"),
    ),
    "VISION": (
        ("OpenCV not available", "WARN", "OpenCV disabled"),
        ("VLM client init failed", "ERR", "VLM provider missing"),
        ("Remote mode: waiting", "IDLE", "Remote mode"),
        ("Loaded 3 person records", "OK", "Person DB loaded"),
    ),
    "MOVE": (
        ("ESP bridge unreachable", "WARN", "ESP bridge unreachable"),
        ("animate degraded", "WARN", "Animation degraded"),
    ),
    "SYS": (
        ("Application startup complete", "OK", "Runtime started"),
        ("Shutting down", "IDLE", "Shutting down"),
    ),
}

@dataclass
class StatusItem:
    name: str
    state: str = "IDLE"
    detail: str = "waiting"
    updated: float = 0.0

@dataclass
class SearchResult:
    path: str
    line: int
    text: str

@dataclass
class AppState:
    root: Path
    active_tab: int = 0
    search: str = ""
    message: str = ""
    selected_config: int = 0
    scroll: int = 0
    config_key: str = ""
    config_value: str = ""
    edit_stage: str = ""
    last_search_results: list[SearchResult] = field(default_factory=list)
    last_search_query: str = ""
    running: bool = True
    robot_status: str = "external/unknown"

class KeyReader:
    def __init__(self) -> None:
        self.is_windows = os.name == "nt"
        self._old_term: Any = None
        if not self.is_windows:
            import termios
            import tty
            self._termios = termios
            self._tty = tty

    def __enter__(self) -> "KeyReader":
        if not self.is_windows and sys.stdin.isatty():
            self._old_term = self._termios.tcgetattr(sys.stdin)
            self._tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_: Any) -> None:
        if not self.is_windows and self._old_term is not None:
            self._termios.tcsetattr(sys.stdin, self._termios.TCSADRAIN, self._old_term)

    def read(self) -> str | None:
        if self.is_windows:
            import msvcrt
            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                nxt = msvcrt.getwch()
                return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}.get(nxt, None)
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
            return {"[A": "UP", "[B": "DOWN", "[D": "LEFT", "[C": "RIGHT"}.get(seq, "ESC")
        if ch in ("\n", "\r"):
            return "ENTER"
        if ch in ("\x7f", "\b"):
            return "BACKSPACE"
        return ch

class RobotProcess:
    def __init__(self, root: Path, enabled: bool) -> None:
        self.root = root
        self.enabled = enabled
        self.proc: subprocess.Popen[str] | None = None
        self.output_log = root / "logs" / "runtime_stdout.log"
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        (self.root / "logs").mkdir(exist_ok=True)
        env = os.environ.copy()
        env.setdefault("SENTRYBOT_AUDIO_PROMPT", "0")
        env.setdefault("PYTHONUNBUFFERED", "1")
        cmd = [sys.executable, "-u", "run_robot.py"]
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

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        with self.output_log.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write("\n--- robot subprocess started %s ---\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            for line in self.proc.stdout:
                fh.write(line)
                fh.flush()

    def state(self) -> str:
        if not self.enabled:
            return "attach"
        if self.proc is None:
            return "not-started"
        code = self.proc.poll()
        if code is None:
            return "running"
        return f"stopped:{code}"

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

class ProjectData:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_candidates = [root / "logs" / "sentry.log", root / "logs" / "runtime_stdout.log"]

    def read_log_lines(self, limit: int = 300) -> list[str]:
        lines: list[str] = []
        for path in self.log_candidates:
            if path.exists():
                lines.extend(_tail(path, limit))
        return lines[-limit:]

    def statuses(self, lines: list[str]) -> dict[str, StatusItem]:
        status = {name: StatusItem(name=name) for name in ["AI", "TTS", "AUDIO", "VISION", "MOVE", "SYS"]}
        for line in lines:
            low = line.lower()
            for name, rules in STATUS_RULES.items():
                for needle, state, detail in rules:
                    if needle.lower() in low:
                        status[name] = StatusItem(name=name, state=state, detail=detail, updated=time.time())
        return status

    def config_files(self) -> list[Path]:
        files: list[Path] = []
        for pattern in ("config/*.yml", "config/*.yaml", "modules/*/config/*.yml", "modules/*/config/*.yaml"):
            files.extend(self.root.glob(pattern))
        return sorted(set(files), key=lambda p: str(p).lower())

    def search_project(self, query: str, limit: int = 150) -> list[SearchResult]:
        if not query.strip():
            return []
        query_l = query.lower()
        results: list[SearchResult] = []
        skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".sentrybot_backups"}
        for path in self.root.rglob("*"):
            if len(results) >= limit:
                break
            if any(part in skip_dirs for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() not in _SEARCH_EXTS:
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                with path.open("r", encoding="utf-8", errors="ignore") as fh:
                    for idx, line in enumerate(fh, 1):
                        if query_l in line.lower():
                            results.append(SearchResult(_rel(self.root, path), idx, line.strip()[:180]))
                            if len(results) >= limit:
                                break
            except Exception:
                continue
        return results

    def set_yaml_value(self, path: Path, dotted_key: str, raw_value: str) -> str:
        if yaml is None:
            return "PyYAML is not installed. Run: pip install PyYAML"
        if not path.exists():
            return "Config file not found"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            value = yaml.safe_load(raw_value)
            node = data
            parts = [p for p in dotted_key.split(".") if p]
            if not parts:
                return "Empty key"
            for part in parts[:-1]:
                if not isinstance(node, dict):
                    return "Parent path is not a mapping"
                node = node.setdefault(part, {})
            if not isinstance(node, dict):
                return "Target parent is not a mapping"
            backup_dir = self.root / ".sentrybot_backups" / ("tui_config_" + time.strftime("%Y%m%d_%H%M%S"))
            backup = backup_dir / _rel(self.root, path)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            node[parts[-1]] = value
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            return f"Saved {dotted_key} -> {value!r}; backup={_rel(self.root, backup_dir)}"
        except Exception as exc:
            return f"Save failed: {exc}"

def _tail(path: Path, limit: int) -> list[str]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = min(size, 96_000)
            fh.seek(max(0, size - block))
            text = fh.read().decode("utf-8", errors="replace")
        return text.splitlines()[-limit:]
    except Exception:
        return []

def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)

def bar(state: str) -> str:
    labels = {
        "OK": "[ OK ]",
        "WARN": "[WARN]",
        "ERR": "[ERR ]",
        "ERROR": "[ERR ]",
        "IDLE": "[IDLE]",
    }
    return labels.get(state.upper(), "[....]")

def box(title: str, body: list[str], width: int) -> list[str]:
    width = max(30, width)
    top = "+-" + title[: max(0, width - 3)].ljust(width - 3, "-") + "+"
    out = [top]
    inner = width - 4
    for line in body:
        chunks = _wrap(line, inner)
        for chunk in chunks or [""]:
            out.append("| " + chunk.ljust(inner) + " |")
    out.append("+" + "-" * (width - 2) + "+")
    return out

def _wrap(text: str, width: int) -> list[str]:
    if width <= 8:
        return [text[:width]]
    if len(text) <= width:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:width])
        text = text[width:]
    return parts

def two_columns(left: list[str], right: list[str], width: int) -> list[str]:
    mid = max(35, width // 2)
    right_w = max(30, width - mid - 1)
    rows = max(len(left), len(right))
    out: list[str] = []
    for idx in range(rows):
        l = left[idx] if idx < len(left) else ""
        r = right[idx] if idx < len(right) else ""
        out.append(l[:mid].ljust(mid) + " " + r[:right_w])
    return out

def clean_line(line: str) -> str:
    line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
    line = line.replace("\r", "")
    return line

def is_important(line: str) -> bool:
    if any(p in line for p in ("ERROR", "WARNING", "WARN", "Robot is bored", "Idle behavior", "Companion", "Wakeword", "VLM", "TTS", "piper", "Vosk", "Google", "ESP bridge")):
        return True
    return not any(p in line for p in NOISE_PATTERNS)

def render_header(state: AppState, robot_state: str, width: int) -> list[str]:
    tabs = ["1 Overview", "2 Logs", "3 Config", "4 Search", "5 Help"]
    tab_line = "  ".join(("[" + t + "]") if i == state.active_tab else " " + t + " " for i, t in enumerate(tabs))
    return box(APP_TITLE, [
        f"Root: {state.root}",
        f"Robot: {robot_state}    Search: {state.search or '-'}",
        tab_line,
        "Keys: 1-5 tabs | / search | arrows scroll/select | e edit config | r refresh | q quit",
    ], width)

def render_overview(state: AppState, data: ProjectData, lines: list[str], width: int, height: int, robot_state: str) -> list[str]:
    statuses = data.statuses(lines)
    left_body = [f"{name.ljust(8)} {bar(item.state)} {item.detail}" for name, item in statuses.items()]
    left_body.append("")
    left_body.append("Detected blockers")
    blockers = blockers_from_lines(lines)
    left_body.extend(blockers or ["none"])
    right_body = [clean_line(x)[-110:] for x in lines if is_important(x)][-max(6, height - 18):]
    left = box(" HEALTH ", left_body, max(38, width // 2 - 1))
    right = box(" RECENT IMPORTANT EVENTS ", right_body or ["No events yet."], max(38, width - len(left[0]) - 1))
    return two_columns(left, right, width)

def blockers_from_lines(lines: list[str]) -> list[str]:
    checks = [
        ("api_key is missing", "AI: Google API key missing"),
        ("piper unavailable", "TTS: Piper voice model missing"),
        ("Vosk TR model missing", "AUDIO: Turkish Vosk model missing"),
        ("Vosk model directory not found", "AUDIO: Vosk model missing"),
        ("OpenCV not available", "VISION: OpenCV unavailable"),
        ("ESP bridge unreachable", "MOVE: ESP bridge unreachable"),
    ]
    found: list[str] = []
    joined = "\n".join(lines[-400:]).lower()
    for needle, label in checks:
        if needle.lower() in joined and label not in found:
            found.append(label)
    return found[:8]

def render_logs(state: AppState, lines: list[str], width: int, height: int) -> list[str]:
    filtered = [clean_line(x) for x in lines if (not state.search or state.search.lower() in x.lower())]
    visible = filtered[max(0, len(filtered) - (height - 10) - state.scroll): len(filtered) - state.scroll if state.scroll else len(filtered)]
    return box(" LOGS ", visible[-max(1, height - 9):] or ["No matching log lines."], width)

def render_config(state: AppState, data: ProjectData, width: int, height: int) -> list[str]:
    files = data.config_files()
    if not files:
        return box(" CONFIG ", ["No YAML config files found."], width)
    state.selected_config = max(0, min(state.selected_config, len(files) - 1))
    selected = files[state.selected_config]
    left_names = []
    for idx, path in enumerate(files[: max(1, height - 10)]):
        prefix = ">" if idx == state.selected_config else " "
        left_names.append(f"{prefix} {idx+1:02d} {_rel(data.root, path)}")
    try:
        text = selected.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        text = [f"read failed: {exc}"]
    preview = [f"File: {_rel(data.root, selected)}", ""] + text[: max(1, height - 13)]
    if state.edit_stage:
        preview.insert(1, f"EDIT {state.edit_stage}: key={state.config_key or '-'} value={state.config_value or '-'}")
    left = box(" FILES ", left_names, max(36, width // 3))
    right = box(" YAML PREVIEW ", preview, max(40, width - len(left[0]) - 1))
    return two_columns(left, right, width)

def render_search(state: AppState, data: ProjectData, width: int, height: int) -> list[str]:
    if state.search and state.search != state.last_search_query:
        state.last_search_results = data.search_project(state.search)
        state.last_search_query = state.search
    body = [f"Query: {state.search or '(press / to search)'}", ""]
    for result in state.last_search_results[: max(0, height - 12)]:
        body.append(f"{result.path}:{result.line}: {result.text}")
    if not state.last_search_results:
        body.append("No results yet.")
    return box(" SEARCH ", body, width)

def render_help(width: int) -> list[str]:
    return box(" HELP ", [
        "This is a separate htop-style control center. It does not print raw robot logs.",
        "Run robot + TUI: python apps/run_robot_tui.py",
        "Attach only:      python apps/sentrybot_tui.py",
        "Tabs: 1 overview, 2 logs, 3 config, 4 search, 5 help.",
        "Search: press /, type text, ENTER. ESC cancels.",
        "Config edit: open Config tab, select YAML with Up/Down, press e.",
        "Then type dotted key, ENTER, value, ENTER. Example: google_ai_studio.api_key", 
        "All config edits are backed up under .sentrybot_backups before saving.",
        "q quits. In run_robot_tui.py it also stops the robot subprocess.",
    ], width)

def render(state: AppState, data: ProjectData, robot: RobotProcess | None) -> str:
    size = shutil.get_terminal_size((110, 34))
    width, height = max(80, size.columns), max(24, size.lines)
    lines = data.read_log_lines(500)
    robot_state = robot.state() if robot else state.robot_status
    out = ["\x1b[H"]
    out.extend(render_header(state, robot_state, width))
    body_h = height - len(out) - 3
    if state.active_tab == 0:
        out.extend(render_overview(state, data, lines, width, body_h, robot_state))
    elif state.active_tab == 1:
        out.extend(render_logs(state, lines, width, body_h))
    elif state.active_tab == 2:
        out.extend(render_config(state, data, width, body_h))
    elif state.active_tab == 3:
        out.extend(render_search(state, data, width, body_h))
    else:
        out.extend(render_help(width))
    if state.message:
        out.extend(box(" MESSAGE ", [state.message], width))
    return "\n".join(out)[:20000]

def handle_key(key: str, state: AppState, data: ProjectData) -> None:
    if state.edit_stage == "search":
        if key == "ENTER":
            state.edit_stage = ""
            state.message = f"Search: {state.search or '-'}"
            state.last_search_query = ""
        elif key == "ESC":
            state.edit_stage = ""
        elif key == "BACKSPACE":
            state.search = state.search[:-1]
        elif len(key) == 1 and key.isprintable():
            state.search += key
        return
    if state.edit_stage == "config_key":
        if key == "ENTER":
            state.edit_stage = "config_value"
        elif key == "ESC":
            state.edit_stage = ""
        elif key == "BACKSPACE":
            state.config_key = state.config_key[:-1]
        elif len(key) == 1 and key.isprintable():
            state.config_key += key
        return
    if state.edit_stage == "config_value":
        if key == "ENTER":
            files = data.config_files()
            if files:
                state.message = data.set_yaml_value(files[state.selected_config], state.config_key, state.config_value)
            state.edit_stage = ""
        elif key == "ESC":
            state.edit_stage = ""
        elif key == "BACKSPACE":
            state.config_value = state.config_value[:-1]
        elif len(key) == 1 and key.isprintable():
            state.config_value += key
        return
    if key in ("q", "Q"):
        state.running = False
    elif key in ("1", "2", "3", "4", "5"):
        state.active_tab = int(key) - 1
        state.scroll = 0
    elif key == "/":
        state.search = ""
        state.edit_stage = "search"
    elif key in ("r", "R"):
        state.message = "Refreshed"
    elif key in ("c", "C"):
        state.search = ""
        state.last_search_query = ""
        state.last_search_results = []
        state.message = "Search cleared"
    elif key == "UP":
        if state.active_tab == 2:
            state.selected_config = max(0, state.selected_config - 1)
        else:
            state.scroll += 1
    elif key == "DOWN":
        if state.active_tab == 2:
            state.selected_config += 1
        else:
            state.scroll = max(0, state.scroll - 1)
    elif key in ("e", "E") and state.active_tab == 2:
        state.config_key = ""
        state.config_value = ""
        state.edit_stage = "config_key"
        state.message = "Type dotted YAML key, ENTER, then value. ESC cancels."

def main(argv: list[str] | None = None, robot: RobotProcess | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT htop-style terminal control center")
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--start-robot", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    if not (root / "run_robot.py").exists():
        print("run_robot.py not found. Start from project root or pass --project-root.")
        return 2
    data = ProjectData(root)
    state = AppState(root=root)
    if robot is None and args.start_robot:
        robot = RobotProcess(root, enabled=True)
        robot.start()
    sys.stdout.write("\x1b[2J\x1b[?25l")
    sys.stdout.flush()
    try:
        with KeyReader() as keys:
            while state.running:
                key = keys.read()
                if key:
                    handle_key(key, state, data)
                sys.stdout.write(render(state, data, robot))
                sys.stdout.flush()
                time.sleep(_REFRESH_S)
    finally:
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()
        if robot is not None:
            robot.stop()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
