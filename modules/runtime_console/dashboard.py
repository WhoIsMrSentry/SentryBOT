from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from typing import Any, Mapping

from .config_loader import load_config
from .event_bus import RuntimeEvent, publish_event
from .panels import render_startup_panel, render_summary_panel, render_warning_panel
from .renderer import ConsoleRenderer

_TRACE_RE = re.compile(r"\b(?:trace|trace_id)[:=]([a-zA-Z0-9_.:-]+)")
_DURATION_RE = re.compile(r"\b(\d{2,6})\s*ms\b", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")

# Messages that are useful in logs/sentry.log but make the live terminal hard to read.
_INFO_NOISE_SUBSTRINGS = (
    "available modules:",
    "press ctrl+c once",
    "started server process",
    "waiting for application startup",
    "application startup complete",
    "uvicorn running on",
    "loaded gateway config:",
    "autonomy owner:",
    "module logs mounted",
    "module admin_ui mounted",
    "module notifier mounted",
    "module social_db mounted",
    "module arduino mounted",
    "module esp_link mounted",
    "module vlm_bridge mounted",
    "module neopixel mounted",
    "module speak mounted",
    "module speech mounted",
    "module ollama mounted",
    "module animate mounted",
    "module piservo mounted",
    "module autonomy mounted",
    "module agent_core mounted",
    "module oled_faces mounted",
    "bridge mounted",
    "wired to interactions engine",
    "integrated successfully",
    "sensor feedback loop started",
    "agent idle heartbeat system started",
    "speecharbiter started",
    "agentorchestrator subsystems started",
    "autonomy brain started",
    "no saved map found",
)

_INFO_KEEP_SUBSTRINGS = (
    "wakeword detected",
    "listening started",
    "robot is bored",
    "idle behavior selected",
    "first audio",
    "reply ready",
    "request approved",
    "completed |",
    "provider mode",
    "remote mode:",
    "piper",
    "vosk",
)


def should_hide_background_message(message: str, hidden_paths: list[str] | tuple[str, ...] | None = None) -> bool:
    paths = hidden_paths or load_config().get("hidden_paths", [])
    return any(path and path in message for path in paths)


def classify_record(record: logging.LogRecord, cfg: Mapping[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    channels = cfg.get("channels") or {}
    text = f"{record.name} {record.getMessage()}".lower()
    for channel, keywords in channels.items():
        for keyword in keywords or []:
            if str(keyword).lower() in text:
                return str(channel).upper()
    return "SYS"


def _status_from_level(level: str) -> str:
    level = level.upper()
    if level in {"ERROR", "CRITICAL"}:
        return "ERROR"
    if level in {"WARNING", "WARN"}:
        return "WARN"
    return "INFO"


def _extract_trace(message: str) -> str | None:
    match = _TRACE_RE.search(message)
    return match.group(1) if match else None


def _extract_duration(message: str) -> int | None:
    match = _DURATION_RE.search(message)
    return int(match.group(1)) if match else None


def _normalize_message(message: str) -> str:
    value = message.lower().strip()
    value = _DIGITS_RE.sub("#", value)
    value = _WS_RE.sub(" ", value)
    return value[:240]


def _is_info_noise(message: str) -> bool:
    text = message.lower()
    if any(keep in text for keep in _INFO_KEEP_SUBSTRINGS):
        return False
    return any(noise in text for noise in _INFO_NOISE_SUBSTRINGS)



def _startup_panel_enabled() -> bool:
    # Return True when the runtime console may print its startup panel.
    #
    # Imports used by audits/tests and safe bootstrap paths must stay quiet. The
    # banner is still allowed during an explicit robot runtime start unless one
    # of the safe-import guards below is set.
    value = str(os.getenv("SENTRYBOT_RUNTIME_CONSOLE_STARTUP_PANEL", "auto")).strip().lower()
    if value in {"1", "true", "yes", "on", "show"}:
        return True
    if value in {"0", "false", "no", "off", "silent", "hide"}:
        return False

    quiet_envs = (
        "SENTRYBOT_DISABLE_AUTOSTART",
        "SENTRYBOT_PI_RUNTIME_AUDIT",
        "SENTRYBOT_ROBOT_TARGET_CODE_AUDIT",
        "SENTRYBOT_GATEWAY_APP_STATUS_PROBE",
    )
    return not any(str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"} for name in quiet_envs)


class RuntimeConsoleLogHandler(logging.Handler):
    """Polished live console for SentryBOT.

    The detailed technical stream still goes to logs/sentry.log. The terminal only
    shows meaningful events, first occurrences of warnings/errors, and short
    summaries for suppressed repeated/background messages.
    """

    def __init__(self, level: int | str = logging.NOTSET, **kwargs: Any) -> None:
        super().__init__(level=level)
        self.cfg = load_config(kwargs)
        self.renderer = ConsoleRenderer(
            colors=bool(self.cfg.get("colors", True)),
            max_width=int(self.cfg.get("max_message_width", 92)),
            border=str(self.cfg.get("border", "rounded")),
        )
        self.mode = str(self.cfg.get("mode", "dashboard")).lower()
        self.hidden_paths = list(self.cfg.get("hidden_paths") or [])
        self.show_background = bool(self.cfg.get("show_background_requests", False))
        self.aggregate = bool(self.cfg.get("aggregate_repeated_messages", True))
        self.summary_interval_s = max(8.0, float(self.cfg.get("repeat_summary_interval_s", 30)))
        self.duplicate_window_s = max(20.0, float(self.cfg.get("duplicate_window_s", 90)))
        self._hidden_count = 0
        self._duplicate_count = 0
        self._last_summary = time.monotonic()
        self._seen: dict[tuple[str, str, str], float] = {}
        self._lock = threading.RLock()
        if _startup_panel_enabled():
            self._write(render_startup_panel(self.renderer, mode=self.mode))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            level = record.levelname.upper()

            if not self.show_background and should_hide_background_message(message, self.hidden_paths):
                self._hidden_count += 1
                self._maybe_emit_summary()
                return

            if level == "INFO" and _is_info_noise(message):
                self._hidden_count += 1
                self._maybe_emit_summary()
                return

            key = (level, record.name, _normalize_message(message))
            now = time.monotonic()
            previous = self._seen.get(key)
            self._seen[key] = now
            if previous is not None and (now - previous) < self.duplicate_window_s:
                self._duplicate_count += 1
                self._maybe_emit_summary()
                return

            channel = classify_record(record, self.cfg)
            event = publish_event(
                channel,
                message,
                level=record.levelname,
                status=_status_from_level(record.levelname),
                trace_id=_extract_trace(message),
                component=record.name,
                duration_ms=_extract_duration(message),
            )
            self._render_event(event)
        except Exception:
            self.handleError(record)

    def _render_event(self, event: RuntimeEvent) -> None:
        if self.mode in {"off", "none"}:
            return
        if event.level in {"WARNING", "ERROR", "CRITICAL"}:
            self._write(render_warning_panel(self.renderer, event))
            return
        # Dashboard mode intentionally avoids redrawing a full EVENT STREAM panel
        # for every INFO event. A single readable event line is easier to follow.
        self._write(self.renderer.event_line(event))

    def _maybe_emit_summary(self) -> None:
        if not self.aggregate:
            return
        now = time.monotonic()
        if now - self._last_summary < self.summary_interval_s:
            return
        hidden = self._hidden_count
        duplicates = self._duplicate_count
        self._hidden_count = 0
        self._duplicate_count = 0
        self._last_summary = now
        parts = []
        if hidden:
            parts.append(f"{hidden} startup/background messages hidden")
        if duplicates:
            parts.append(f"{duplicates} repeated messages collapsed")
        if parts:
            self._write(render_summary_panel(self.renderer, " | ".join(parts)))

    def _write(self, text: str) -> None:
        with self._lock:
            sys.stdout.write(text.rstrip() + "\n")
            sys.stdout.flush()