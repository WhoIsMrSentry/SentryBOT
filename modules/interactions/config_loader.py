from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def load_config(config_path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load YAML config for interactions module with sane defaults.

    Priority: explicit path > modules/interactions/config/config.yml > defaults
    """
    base = {
        "server": {"host": "0.0.0.0", "port": 8095},
        "adapter": {"mode": "http", "http_base_url": "http://localhost:8092/neopixel"},
        "hardware": {
            "num_leds": 23,
            "segments": [
                {"name": "jewel", "start": 0, "count": 7, "reverse": False},
                {"name": "stick", "start": 7, "count": 16, "reverse": False},
            ],
        },
        "thresholds": {
            "cpu_temp": {"warm": 65, "hot": 75, "hysteresis": 3},
            "cpu_load": {"high": 0.9, "window_s": 60},
            "net": {"burst_mbps": 20, "min_duration_ms": 200},
        },
        "defaults": {
            "brightness": 0.6,
            "idle": {"base": {"name": "BREATHE", "color": "#30E3CA", "speed": "slow"}},
        },
        "rules": [],
    }

    p = config_path
    if not p:
        here = os.path.dirname(__file__)
        p = os.path.join(here, "config", "config.yml")

    data: Dict[str, Any] = {}
    if p and os.path.exists(p) and yaml is not None:
        with open(p, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                data = loaded

    # merge shallowly
    def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        r = dict(a)
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(r.get(k), dict):
                r[k] = _merge(r[k], v)  # type: ignore
            else:
                r[k] = v
        return r

    cfg = _merge(base, data)
    if overrides:
        cfg = _merge(cfg, overrides)
    return cfg
