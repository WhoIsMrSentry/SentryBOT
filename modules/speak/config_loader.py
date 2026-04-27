from __future__ import annotations
import os
from copy import deepcopy
from typing import Any, Dict
from modules.config_center.agent_yaml_loader import load_agent_config, require_dict_section


def _normalize_speak_section(section: Dict[str, Any]) -> Dict[str, Any]:
    """Keep agent.yaml as single source, with small compatibility aliases.

    Supports legacy shorthand keys like `speak.engine` by mapping them into
    `speak.tts.engine` when present.
    """
    out = deepcopy(section)
    tts = out.get("tts") if isinstance(out.get("tts"), dict) else {}
    out["tts"] = dict(tts)

    # Compatibility: allow `speak.engine: xtts` as shorthand.
    shorthand_engine = str(out.get("engine", "")).strip()
    if shorthand_engine:
        out["tts"]["engine"] = shorthand_engine

    return out


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load speak config from central config/agent.yaml.

    Strict mode: module-local config.yml is not used.
    """
    root_cfg = load_agent_config(override_path)
    section = require_dict_section(root_cfg, "speak")
    return _normalize_speak_section(section)
