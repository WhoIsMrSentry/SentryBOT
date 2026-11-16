from __future__ import annotations
import os
from copy import deepcopy
from typing import Any, Dict
from modules.common.config_loader import load_agent_config, require_dict_section
from modules.voice.audio_router import load_audio_router_config


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load speech config from central config/agent.yaml.

    Strict mode: module-local config.yml is not used.
    """
    explicit = override_path or os.getenv("SPEECH_CONFIG")
    root_cfg = load_agent_config(explicit)
    section = require_dict_section(root_cfg, "speech")
    
    # Add audio_router config if present
    audio_router_cfg = root_cfg.get("audio_router")
    if isinstance(audio_router_cfg, dict):
        section["audio_router"] = audio_router_cfg
    
    return deepcopy(section)


__all__ = ["load_config", "load_audio_router_config"]
