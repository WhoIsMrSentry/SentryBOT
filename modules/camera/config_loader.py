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
    """Load YAML config for camera module.

    Priority:
    1. provided path
    2. CAM_CONFIG env var
    3. default config.yml in module
    """
    cfg_path = Path(path) if path else Path(os.getenv("CAM_CONFIG", _DEFAULT_CFG_PATH))
    if not cfg_path.exists():
        # fallback to default bundled
        cfg_path = _DEFAULT_CFG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Environment overrides (flat small set for simplicity)
    env_overrides: Dict[str, Any] = {}
    backend = os.getenv("CAM_BACKEND")
    if backend:
        env_overrides["backend"] = backend
    source = os.getenv("CAM_SOURCE")
    if source:
        # try int, else keep string
        try:
            env_overrides["source"] = int(source)
        except ValueError:
            env_overrides["source"] = source
    w = os.getenv("CAM_WIDTH")
    h = os.getenv("CAM_HEIGHT")
    if w or h:
        env_overrides.setdefault("resolution", {})
        if w:
            env_overrides["resolution"]["width"] = int(w)
        if h:
            env_overrides["resolution"]["height"] = int(h)
    fps = os.getenv("CAM_FPS")
    if fps:
        env_overrides["fps_target"] = int(fps)
    q = os.getenv("CAM_JPEG_QUALITY")
    if q:
        env_overrides["jpeg_quality"] = int(q)
    flip = os.getenv("CAM_FLIP")
    if flip:
        env_overrides["flip"] = flip
    enabled = os.getenv("CAM_ENABLED")
    if enabled is not None:
        env_overrides["enabled"] = str(enabled).strip().lower() in {"1", "true", "yes", "on"}
    return _deep_update(data, env_overrides)
