from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..config_loader import DEFAULT_HIDDEN_PATHS, load_yaml_with_defaults

DEFAULT_CONFIG: Dict[str, Any] = {
    "enable_console": True,
    "console_level": "INFO",
    "console": {
        "mode": "dashboard",
        "colors": True,
        "show_background_requests": False,
        "aggregate_repeated_messages": True,
        "repeat_summary_interval_s": 30,
        "event_history": 8,
        "max_message_width": 92,
        "border": "rounded",
        "hidden_paths": list(DEFAULT_HIDDEN_PATHS),
    },
    "enable_file": True,
    "file_path": "logs/sentry.log",
    "rotate_bytes": 2 * 1024 * 1024,  # 2MB
    "backup_count": 5,
    "json_format": False,
    "buffer_size": 1000,  # in-memory ring buffer size
    "capture_warnings": True,
    # Per-module level overrides, e.g. {"uvicorn": "WARNING"}
    "module_levels": {
        "uvicorn.access": "WARNING",
        "httpx": "WARNING",
        "httpcore": "WARNING",
        "urllib3.connectionpool": "WARNING",
    },
    "separate_files": {
        "enabled": False,
        "warnings_path": "logs/warnings.log",
        "errors_path": "logs/errors.log",
        "tui_path": "logs/tui.log",
    },
}


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """YAML config.yml dosyasını ve opsiyonel override'ları yükler.

    Arama sırası:
    - base_dir altında config/config.yml (eğer verildiyse)
    - modules/runtime_console/logwrapper/config/config.yml

    overrides sözlüğü sağlanırsa, YAML üzerindeki değerlere baskın gelir.
    """
    candidates: list[Path] = []
    if base_dir:
        candidates.append(Path(base_dir) / "config" / "config.yml")
    candidates.append(Path(__file__).resolve().parent / "config" / "config.yml")

    cfg = load_yaml_with_defaults(DEFAULT_CONFIG, candidates, overrides=overrides)

    # Normalize env overrides (e.g., LOG_LEVEL, LOG_FILE)
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        cfg["console_level"] = env_level
    env_file = os.getenv("LOG_FILE")
    if env_file:
        cfg["file_path"] = env_file

    return cfg
