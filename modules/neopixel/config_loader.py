from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

import yaml

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load YAML config for neopixel module.

    Priority:
    1. provided path
    2. NEO_CONFIG env var
    3. default config.yml in module
    """
    cfg_path = Path(path) if path else Path(os.getenv("NEO_CONFIG", _DEFAULT_CFG_PATH))
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    env: Dict[str, Any] = {}
    dev = os.getenv("NEO_DEVICE")
    if dev:
        env.setdefault("hardware", {})["device"] = dev
    n = os.getenv("NEO_NUM_LEDS")
    if n:
        env.setdefault("hardware", {})["num_leds"] = int(n)
    spd = os.getenv("NEO_SPEED_KHZ")
    if spd:
        env.setdefault("hardware", {})["speed_khz"] = int(spd)
    backend = os.getenv("NEO_BACKEND")
    if backend:
        env.setdefault("hardware", {})["backend"] = backend
    wspd = os.getenv("NEO_WS2812_SPI_KHZ")
    if wspd:
        env.setdefault("hardware", {})["ws2812_spi_khz"] = int(wspd)
    order = os.getenv("NEO_ORDER")
    if order:
        env.setdefault("hardware", {})["order"] = order
    host = os.getenv("NEO_HOST")
    if host:
        env.setdefault("server", {})["host"] = host
    port = os.getenv("NEO_PORT")
    if port:
        env.setdefault("server", {})["port"] = int(port)
    return _deep_update(data, env)
