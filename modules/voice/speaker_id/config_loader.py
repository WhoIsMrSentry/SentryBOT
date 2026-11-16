"""Config loader for the speaker_id service."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from modules.common.bind_host import apply_bind_host
from modules.common.config_loader import deep_merge, load_agent_config

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_store_path(raw: Any) -> str:
    text = str(raw or "data/speaker_id.json").strip() or "data/speaker_id.json"
    p = Path(text)
    if p.is_absolute():
        return str(p)
    return str((_REPO_ROOT / p).resolve())


def load_config(config_path: str | None = None, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base_path = Path(__file__).resolve().parent / "config" / "config.yml"
    cfg: Dict[str, Any] = {}
    if base_path.is_file():
        cfg = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}

    if config_path:
        explicit = Path(config_path)
        if explicit.is_file():
            loaded = yaml.safe_load(explicit.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                cfg = deep_merge(cfg, loaded.get("speaker_id") if isinstance(loaded.get("speaker_id"), dict) else loaded)
    else:
        try:
            agent_cfg = load_agent_config() or {}
            section = agent_cfg.get("speaker_id")
            if isinstance(section, dict):
                cfg = deep_merge(cfg, section)
        except Exception:
            pass

    if isinstance(overrides, dict) and overrides:
        cfg = deep_merge(cfg, overrides)

    threshold = cfg.get("threshold")
    if not isinstance(threshold, dict):
        cfg["threshold"] = {"similarity": 0.75, "margin": 0.05}
    cfg["store_path"] = _resolve_store_path(cfg.get("store_path"))
    return apply_bind_host(cfg, "SPEAKER_ID_HOST")
