from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml is optional in fallback-only tests
    yaml = None

_DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "dashboard",
    "colors": True,
    "show_background_requests": False,
    "aggregate_repeated_messages": True,
    "repeat_summary_interval_s": 30,
    "event_history": 8,
    "max_message_width": 92,
    "border": "rounded",
    "hidden_paths": [
        "/camera/healthz",
        "/vlm/context/latest",
        "/vlm/results/latest",
        "/telemetry/metrics",
        "/speech/last",
        "/speech/direction",
        "/arduino/healthz",
        "/state/set/emotions",
        "/interactions/event",
        "/interactions/effect",
        "/neopixel/animate",
        "/oled_faces/manual",
    ],
    "channels": {
        "CORE": ["gateway", "run_robot", "startup", "server", "scheduler"],
        "AUDIO": ["speech", "wakeword", "stt", "microphone", "audio", "alsa", "openwakeword"],
        "TTS": ["speak", "tts", "piper", "glados", "voice"],
        "VISION": ["camera", "vlm", "imx500", "qwen", "vision", "face", "object"],
        "AI": ["agent", "llm", "ollama", "google", "gemini", "tool", "planner"],
        "FACE": ["neopixel", "oled", "expression", "emotion", "mood"],
        "MOVE": ["arduino", "servo", "stepper", "motor", "piservo", "animate"],
        "MEMORY": ["memory", "rag", "recall", "relationship", "social"],
    },
}


def _deep_merge(base: dict[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _env_bool(name: str, current: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return current
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(_DEFAULT_CONFIG)
    path = Path(__file__).resolve().parent / "config" / "config.yml"
    if yaml is not None and path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if isinstance(data, Mapping):
                cfg = _deep_merge(cfg, data)
        except Exception:
            cfg = dict(_DEFAULT_CONFIG)
    if overrides:
        cfg = _deep_merge(cfg, overrides)

    mode = os.getenv("SENTRYBOT_CONSOLE_MODE")
    if mode:
        cfg["mode"] = mode.strip().lower()
    cfg["colors"] = _env_bool("SENTRYBOT_CONSOLE_COLORS", bool(cfg.get("colors", True)))
    cfg["show_background_requests"] = _env_bool(
        "SENTRYBOT_SHOW_BACKGROUND_REQUESTS",
        bool(cfg.get("show_background_requests", False)),
    )
    return cfg
