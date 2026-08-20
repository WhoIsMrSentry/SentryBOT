from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # Lazy optional dependency


DEFAULT_CONFIG: Dict[str, Any] = {
    "enable_console": True,
    "console_level": "INFO",
    "enable_file": True,
    "file_path": "logs/sentry.log",
    "rotate_bytes": 2 * 1024 * 1024,  # 2MB
    "backup_count": 5,
    "json_format": False,
    "buffer_size": 1000,  # in-memory ring buffer size
    "capture_warnings": True,
    # Per-module level overrides, e.g. {"uvicorn": "WARNING"}
    "module_levels": {},
}


def load_config(base_dir: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """YAML config.yml dosyasını ve opsiyonel override'ları yükler.

    Arama sırası:
    - modules/logwrapper/config/config.yml
    - base_dir altında config/config.yml (eğer verildiyse)

    overrides sözlüğü sağlanırsa, YAML üzerindeki değerlere baskın gelir.
    """
    cfg: Dict[str, Any] = dict(DEFAULT_CONFIG)

    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "config", "config.yml"))
    # Default module path
    here = os.path.dirname(__file__)
    candidates.append(os.path.join(here, "config", "config.yml"))

    for path in candidates:
        if os.path.exists(path):
            if yaml is None:
                break
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                cfg.update(data)
            break

    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})

    # Normalize env overrides (e.g., LOG_LEVEL, LOG_FILE)
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        cfg["console_level"] = env_level
    env_file = os.getenv("LOG_FILE")
    if env_file:
        cfg["file_path"] = env_file

    return cfg
