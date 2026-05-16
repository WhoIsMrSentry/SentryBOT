from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml


def _repo_root() -> Path:
    # modules/config_center/agent_yaml_loader.py -> repo root is 2 parents up
    return Path(__file__).resolve().parents[2]


def _candidate_paths(explicit_path: Optional[str | os.PathLike[str]] = None) -> Iterable[Path]:
    if explicit_path:
        yield Path(explicit_path)

    env_path = str(os.getenv("AGENT_CFG", "")).strip()
    if env_path:
        yield Path(env_path)

    yield _repo_root() / "config" / "agent.yaml"
    yield Path("config") / "agent.yaml"


def resolve_agent_cfg_path(explicit_path: Optional[str | os.PathLike[str]] = None) -> Path:
    seen: set[str] = set()
    checked: list[str] = []

    for candidate in _candidate_paths(explicit_path):
        norm = os.path.normcase(os.path.normpath(str(candidate)))
        if norm in seen:
            continue
        seen.add(norm)
        checked.append(str(candidate))

        if candidate.exists() and candidate.is_file():
            return candidate

    searched = ", ".join(checked) if checked else "<none>"
    raise FileNotFoundError(
        "agent.yaml not found. Set AGENT_CFG or create config/agent.yaml. "
        f"Searched: {searched}"
    )


def load_agent_config(explicit_path: Optional[str | os.PathLike[str]] = None) -> Dict[str, Any]:
    from modules.config_center.runtime_profile import apply_runtime_profile

    cfg_path = resolve_agent_cfg_path(explicit_path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"agent.yaml must be a mapping at top-level: {cfg_path}")
    return apply_runtime_profile(raw)


def require_dict_section(cfg: Dict[str, Any], section: str) -> Dict[str, Any]:
    data = cfg.get(section)
    if not isinstance(data, dict):
        raise KeyError(f"agent.yaml missing required section: {section}")
    return data


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(dict(out[key]), value)
        else:
            out[key] = value
    return out
