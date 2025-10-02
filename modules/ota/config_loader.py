from __future__ import annotations
import os
from typing import Any, Dict
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8097},
    "include": {"api": True},
    "ota": {
        "watch_dir": "arduino/firmware/xMain/build",  # derleme çıktılarının düştüğü klasör
        "artifact_glob": "*.hex",  # avrdude için varsayılan hex
        "board": {
            "mcu": "atmega328p",
            "programmer": "arduino",  # stk500v1 vb.
            "baud": 115200,
            "port": "/dev/ttyUSB0"  # Windows için COM3 gibi
        },
        "avrdude": {
            "bin": "avrdude",
            "config": None,  # özel avrdude.conf yolu (opsiyonel)
            "extra_flags": []
        },
        "version_db": "modules/ota/config/versions.json",
        "scan_on_start": True
    }
}


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("OTA_CFG", "modules/ota/config/config.yml")
    data: Dict[str, Any] = {}
    if path and os.path.exists(path) and yaml is not None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    # shallow merge + deep for dicts
    cfg: Dict[str, Any] = DEFAULT_CFG.copy()
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
