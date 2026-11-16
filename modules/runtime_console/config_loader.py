from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml is optional in fallback-only tests
    yaml = None

from modules.common.config_loader import deep_merge

DEFAULT_HIDDEN_PATHS: tuple[str, ...] = (
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
)

_DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "dashboard",
    "colors": True,
    "show_background_requests": False,
    "aggregate_repeated_messages": True,
    "repeat_summary_interval_s": 30,
    "event_history": 8,
    "max_message_width": 92,
    "border": "rounded",
    "hidden_paths": list(DEFAULT_HIDDEN_PATHS),
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


def _env_bool(name: str, current: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return current
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_yaml_with_defaults(
    defaults: Mapping[str, Any],
    candidates: list[Path],
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load the first existing YAML candidate and deep-merge with defaults and overrides."""
    cfg = copy.deepcopy(dict(defaults))
    for target_path in candidates:
        if target_path.exists():
            if yaml is None:
                break
            try:
                with target_path.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                if isinstance(data, Mapping):
                    cfg = deep_merge(cfg, dict(data))
            except Exception:
                cfg = copy.deepcopy(dict(defaults))
            break
    if overrides and isinstance(overrides, Mapping):
        clean_overrides = {k: v for k, v in overrides.items() if v is not None}
        cfg = deep_merge(cfg, clean_overrides)
    return cfg


def load_config(
    config_path: str | os.PathLike | Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(config_path, Mapping) and overrides is None:
        overrides = config_path
        config_path = None

    default_path = Path(__file__).resolve().parent / "config" / "config.yml"
    candidates = [Path(config_path)] if config_path else [default_path]
    cfg = load_yaml_with_defaults(_DEFAULT_CONFIG, candidates, overrides=overrides)

    mode = os.getenv("SENTRYBOT_CONSOLE_MODE")
    if mode:
        cfg["mode"] = mode.strip().lower()
    cfg["colors"] = _env_bool("SENTRYBOT_CONSOLE_COLORS", bool(cfg.get("colors", True)))
    cfg["show_background_requests"] = _env_bool(
        "SENTRYBOT_SHOW_BACKGROUND_REQUESTS",
        bool(cfg.get("show_background_requests", False)),
    )
    return cfg
