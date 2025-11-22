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
    """Windows camera config loader with env overrides.

    Priority: path > CAM_CONFIG env > bundled default
    """
    cfg_path = Path(path) if path else Path(os.getenv("CAM_CONFIG", _DEFAULT_CFG_PATH))
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Force Windows backend to opencv by default
    data.setdefault("backend", "opencv")
    # Environment overrides
    env: Dict[str, Any] = {}
    backend = os.getenv("CAM_BACKEND")
    if backend:
        env["backend"] = backend
    source = os.getenv("CAM_SOURCE")
    if source:
        try:
            env["source"] = int(source)
        except ValueError:
            env["source"] = source
    w = os.getenv("CAM_WIDTH")
    h = os.getenv("CAM_HEIGHT")
    if w or h:
        env.setdefault("resolution", {})
        if w:
            env["resolution"]["width"] = int(w)
        if h:
            env["resolution"]["height"] = int(h)
    fps = os.getenv("CAM_FPS")
    if fps:
        env["fps_target"] = int(fps)
    q = os.getenv("CAM_JPEG_QUALITY")
    if q:
        env["jpeg_quality"] = int(q)
    flip = os.getenv("CAM_FLIP")
    if flip:
        env["flip"] = flip
    return _deep_update(data, env)
