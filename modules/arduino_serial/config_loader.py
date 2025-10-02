from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

DEFAULT_CONFIG: Dict[str, Any] = {
    "port": "COM3",  # Windows default guess; override via env or config
    "baudrate": 115200,
    "timeout": 0.05,  # read timeout seconds
    "write_timeout": 0.1,
    "reconnect_sec": 2.0,
    "heartbeat_ms": 100,
    "auto_heartbeat": True,
    "telemetry": {"enabled": False, "interval_ms": 100},
    "log_level": "INFO",
}


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load config/config.yml and apply overrides & env.

    Search order:
    - base_dir/config/config.yml if provided
    - modules/arduino_serial/config/config.yml
    """
    cfg: Dict[str, Any] = dict(DEFAULT_CONFIG)

    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "config", "config.yml"))
    here = os.path.dirname(__file__)
    candidates.append(os.path.join(here, "config", "config.yml"))

    for path in candidates:
        if os.path.exists(path) and yaml is not None:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                cfg.update(data)
            break

    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})

    # env overrides
    env_port = os.getenv("ARDUINO_PORT")
    if env_port:
        cfg["port"] = env_port
    env_baud = os.getenv("ARDUINO_BAUD")
    if env_baud and env_baud.isdigit():
        cfg["baudrate"] = int(env_baud)

    return cfg
