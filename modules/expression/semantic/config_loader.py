from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

logger = logging.getLogger("expression.semantic.config_loader")

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8111},
    "state": {
        "default_emotion": "neutral",
        "default_arousal": "low",
        "default_attention": "idle",
        "default_energy": "normal",
        "max_history": 120,
    },
    "mappings": {
        "colors": {
            "neutral": "#4060ff",
            "curious": "#00bcd4",
            "happy": "#00ff88",
            "sleepy": "#101522",
            "alert": "#ffb000",
            "sad": "#2050ff",
            "thinking": "#7a5cff",
            "listening": "#00aaff",
            "speaking": "#00ffcc",
        },
        "oled_moods": {
            "neutral": "neutral",
            "curious": "curious",
            "happy": "happy",
            "sleepy": "sleepy",
            "alert": "alert",
            "sad": "sad",
            "thinking": "thinking",
        },
        "led_modes": {
            "idle": "eye",
            "user": "listen",
            "sound": "pulse",
            "object": "eye",
            "sleep": "off",
            "internal": "thinking",
            "camera": "eye",
        },
    },
    "arbiter": {
        "min_interval_s": 0.5,
        "visual_lock_default_s": 2.2,
        "visual_lock_strong_s": 4.5,
        "visual_state_hold_s": 3.0,
    },
    "output_bridge": {
        "enabled": True,
        "gateway_url": "http://127.0.0.1:8080",
        "timeout_s": 0.8,
        "endpoints": {
            "neopixel": "/neopixel/companion/mode",
            "oled_faces": "/oled_faces/event",
            "piservo": "/piservo/gesture",
        },
    },
    "adapters": {
        "enabled": True,
        "gateway_url": "http://127.0.0.1:8080",
        "neopixel_timeout": 2.0,
        "oled_timeout": 2.0,
        "speak_timeout": 4.0,
        "head_timeout": 1.0,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)  # type: ignore[arg-type]
        else:
            out[key] = value
    return out


def load_config(config_path: str | None = None, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else Path(__file__).parent / "config" / "config.yml"
    data: Dict[str, Any] = dict(DEFAULT_CONFIG)
    if path.exists() and yaml is not None:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                data = _deep_merge(data, loaded)
        except Exception as exc:
            logger.warning("Failed to parse expression semantic config '%s': %s", path, exc)
    if overrides:
        data = _deep_merge(data, overrides)
    try:
        from modules.gateway.url import resolve_gateway_base_url, rewrite_loopback_urls

        data = rewrite_loopback_urls(data, resolve_gateway_base_url())
    except Exception:
        pass
    return data
