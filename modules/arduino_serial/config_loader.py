from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

from modules.common.config_loader import deep_merge

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

DEFAULT_CONFIG: Dict[str, Any] = {
    "transport": "esp_http",
    "esp_base_url": "http://sentrybot-2.local:8080",
    "esp_request_path": "/request",
    "esp_send_path": "/send",
    "esp_health_path": "/healthz",
    "esp_timeout_sec": 2.5,
    "esp_connect_timeout_sec": 1.5,
    "esp_pause_after_failures": 5,
    "esp_pause_sec": 120.0,
    "port": "AUTO",  # Prefer autodetect; override via env or config
    "baudrate": 115200,
    "timeout": 0.05,  # read timeout seconds
    "write_timeout": 0.1,
    "reconnect_sec": 2.0,
    "heartbeat_ms": 2000,
    "auto_heartbeat": True,
    "request_max_retries": 1,
    "request_timeout_ms": 2000,
    "strict_request_correlation": False,
    "min_firmware_version": "",
    "required_capabilities": [],
    "watchdog": {
        "enabled": True,
        "timeout_s": 6.0,
        "check_interval_s": 0.5,
        "only_while_moving": False,
    },
    "telemetry": {"enabled": False, "interval_ms": 100, "endpoint": None},
    "log_level": "INFO",
    "rfid": {
        "allowed_uids": [],
        "authorize_window_s": 8.0,
    },
}


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load config/config.yml and apply overrides & env.

    Search order:
    - base_dir/config/config.yml if provided
    - modules/arduino_serial/config/config.yml
    """
    cfg: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)

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
                cfg = deep_merge(cfg, data)
            break

    try:
        from modules.common.config_loader import load_agent_config

        root = load_agent_config()
        serial_cfg = root.get("arduino_serial")
        if isinstance(serial_cfg, dict):
            cleaned = {k: v for k, v in serial_cfg.items() if v is not None}
            cfg = deep_merge(cfg, cleaned)
    except Exception:
        pass

    if overrides:
        cleaned = {k: v for k, v in overrides.items() if v is not None}
        cfg = deep_merge(cfg, cleaned)

    env_esp = os.getenv("SENTRYBOT_ESP_BASE_URL", "").strip()
    if env_esp:
        cfg["esp_base_url"] = env_esp

    env_port = os.getenv("ARDUINO_PORT")
    if env_port:
        cfg["port"] = env_port
    env_baud = os.getenv("ARDUINO_BAUD")
    if env_baud and env_baud.isdigit():
        cfg["baudrate"] = int(env_baud)

    return cfg
