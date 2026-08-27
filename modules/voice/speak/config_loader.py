from __future__ import annotations
SPEAK_CONFIG_COMPATIBILITY_CONTRACT = True
SPEAK_CONFIG_COMPATIBILITY_ROLE = "agent_yaml_shorthand_alias_normalizer"

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict
from modules.common.config_loader import load_agent_config, require_dict_section

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _abs_from_repo(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return text
    path = Path(text)
    if path.is_absolute() and path.exists():
        return str(path)
    candidates = [
        _REPO_ROOT / path,
        _REPO_ROOT.parent / path,
        Path.cwd() / path,
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand.resolve())
    return str((_REPO_ROOT / path).resolve())


def _resolve_piper_paths(piper: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(piper, dict):
        return {}
    out = dict(piper)
    if out.get("model_path"):
        out["model_path"] = _abs_from_repo(out["model_path"])
    if out.get("config_path"):
        out["config_path"] = _abs_from_repo(out["config_path"])
    voices = out.get("voices", {})
    if isinstance(voices, dict):
        resolved_voices: Dict[str, Any] = {}
        for key, entry in voices.items():
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            if item.get("model_path"):
                item["model_path"] = _abs_from_repo(item["model_path"])
            if item.get("config_path"):
                item["config_path"] = _abs_from_repo(item["config_path"])
            resolved_voices[str(key)] = item
        out["voices"] = resolved_voices
    return out


def _normalize_speak_section(section: Dict[str, Any]) -> Dict[str, Any]:
    """Keep agent.yaml as single source, with small compatibility aliases.

    Supports compatibility shorthand keys like `speak.engine` by mapping them into
    `speak.tts.engine` when present.
    """
    out = deepcopy(section)
    tts = out.get("tts") if isinstance(out.get("tts"), dict) else {}
    out["tts"] = dict(tts)

    # Compatibility alias: allow `speak.engine: xtts` as shorthand.
    shorthand_engine = str(out.get("engine", "")).strip()
    if shorthand_engine:
        out["tts"]["engine"] = shorthand_engine

    piper = out.get("tts", {}).get("piper", {})
    if isinstance(piper, dict):
        out["tts"]["piper"] = _resolve_piper_paths(piper)

    return out


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load speak config from central config/agent.yaml.

    Strict mode: module-local config.yml is not used.
    """
    root_cfg = load_agent_config(override_path)
    section = require_dict_section(root_cfg, "speak")
    return _normalize_speak_section(section)
