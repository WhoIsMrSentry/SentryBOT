"""Config loader for the speaker_id service."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def load_config(config_path: str | None = None, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base_dir = Path(__file__).resolve().parent.parent / "config" / "config.yml"
    path = Path(config_path) if config_path else base_dir
    cfg: Dict[str, Any] = {}
    if path.is_file():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(overrides, dict) and overrides:
        cfg = {**cfg, **overrides}
    threshold = cfg.get("threshold")
    if not isinstance(threshold, dict):
        cfg["threshold"] = {"similarity": 0.75, "margin": 0.05}
    return cfg
