from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

from .console_types import (
    CHANNEL_HINTS,
    COMPACT_RE,
    LEVEL_ORDER,
    LOG_RE,
    MAX_SEARCH_FILE_BYTES,
    NOISE_HINTS,
    PC_EXPECTED_HINTS,
    SEARCH_EXTS,
    LogEvent,
    SearchResult,
    ServiceStatus,
    Snapshot,
    UIState,
)
from .console_formatting import clean_path, safe_text, strip_ansi


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


def filter_events(events: Iterable[LogEvent], text: str, include_debug: bool) -> list[LogEvent]:
    result: list[LogEvent] = []
    text_l = text.lower().strip()
    for ev in events:
        is_debug = getattr(ev, "_is_debug", ev.level.upper() == "DEBUG")
        if not include_debug and is_debug:
            continue
        if text_l:
            blob = getattr(ev, "_search_blob", None)
            if blob is None:
                blob = f"{ev.raw} {ev.message} {ev.source} {ev.channel}".lower()
            if text_l not in blob:
                continue
        result.append(ev)
    return result


def is_low_value_startup(ev: LogEvent) -> bool:
    msg = ev.message.lower()
    if getattr(ev, "_is_debug", ev.level.upper() == "DEBUG"):
        return True
    if any(h.lower() in msg for h in NOISE_HINTS):
        return True
    is_warn_err = getattr(ev, "_is_warn_or_err", ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"})
    if is_warn_err:
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
        x in service_text for x in ("speech_recognition", "openwakeword", "stt unavailable", "microphone")
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
    cache_key = (getattr(snapshot, "events_version", len(snapshot.events)), filter_text, ui.log_view.lower(), ui.profile, include_debug)
    cached = getattr(snapshot, "_view_cache", None)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    events = filter_events(snapshot.events, filter_text, include_debug)
    view = ui.log_view.lower()
    if view == "warn":
        events = [ev for ev in events if getattr(ev, "_is_warn_or_err", ev.level.upper().replace("WARNING", "WARN") in {"WARN", "ERROR", "CRITICAL"})]
    elif view == "human" and not filter_text:
        events = [ev for ev in events if not is_low_value_startup(ev)]
        if ui.profile == "pc-test":
            events = [
                ev
                for ev in events
                if not (
                    getattr(ev, "_is_warn_or_err", False)
                    and event_is_pc_expected(ev)
                )
            ]
    snapshot._view_cache = (cache_key, events)
    return events


def current_log_events(snapshot: Snapshot, ui: UIState, include_debug: bool | None = None) -> list[LogEvent]:
    return events_for_view(snapshot, ui, include_debug=include_debug)


def newest_first_events(snapshot: Snapshot, ui: UIState) -> list[LogEvent]:
    evs = current_log_events(snapshot, ui)
    rev_key = (getattr(snapshot, "events_version", len(snapshot.events)), ui.filter_text, ui.log_view.lower(), ui.profile)
    cached = getattr(snapshot, "_newest_cache", None)
    if cached is not None and cached[0] == rev_key:
        return cached[1]
    res = list(reversed(evs))
    snapshot._newest_cache = (rev_key, res)
    return res


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
    elif "speech/stt unavailable" in msg or "stt backend unavailable" in msg:
        out += [
            "Speech recognition backend unavailable.",
            "PC test: expected if SpeechRecognition is not installed.",
            "Robot: run pip install SpeechRecognition.",
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
