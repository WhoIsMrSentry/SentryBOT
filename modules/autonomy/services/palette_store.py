from __future__ import annotations
"""Helpers to read and mutate Autonomy light palettes on disk."""

from pathlib import Path
from typing import Dict, Sequence
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.yml"


def _resolve_path(path: str | Path | None) -> Path:
    if path is None:
        return CONFIG_PATH
    return Path(path)


def _load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _dump_yaml(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def _ensure_palette_dict(config: Dict) -> Dict[str, list[int]]:
    defaults = config.setdefault("defaults", {})
    lights = defaults.setdefault("lights", {})
    palettes = lights.setdefault("palettes", {})
    return palettes


def list_palettes(config_path: str | Path | None = None) -> Dict[str, list[int]]:
    path = _resolve_path(config_path)
    cfg = _load_yaml(path)
    palettes = cfg.get("defaults", {}).get("lights", {}).get("palettes", {})
    return dict(palettes) if isinstance(palettes, dict) else {}


def _normalize_rgb(rgb: Sequence[int]) -> list[int]:
    values = list(rgb)
    if len(values) != 3:
        raise ValueError("RGB value requires exactly 3 components")
    normalized: list[int] = []
    for component in values:
        normalized.append(max(0, min(255, int(component))))
    return normalized


def set_palette(name: str, rgb: Sequence[int], config_path: str | Path | None = None) -> Dict[str, list[int]]:
    if not name:
        raise ValueError("Palette name cannot be empty")
    path = _resolve_path(config_path)
    cfg = _load_yaml(path)
    palettes = _ensure_palette_dict(cfg)
    palettes[name] = _normalize_rgb(rgb)
    _dump_yaml(path, cfg)
    return dict(palettes)


def remove_palette(name: str, config_path: str | Path | None = None) -> Dict[str, list[int]]:
    if not name:
        raise ValueError("Palette name cannot be empty")
    path = _resolve_path(config_path)
    cfg = _load_yaml(path)
    palettes = _ensure_palette_dict(cfg)
    if name not in palettes:
        raise KeyError(name)
    palettes.pop(name)
    _dump_yaml(path, cfg)
    return dict(palettes)


__all__ = [
    "CONFIG_PATH",
    "list_palettes",
    "set_palette",
    "remove_palette",
]
