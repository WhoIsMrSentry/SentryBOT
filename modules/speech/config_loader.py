from __future__ import annotations
import os
from copy import deepcopy
from typing import Any, Dict
from modules.config_center.agent_yaml_loader import load_agent_config, require_dict_section


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load speech config from central config/agent.yaml.

    Strict mode: module-local config.yml is not used.
    """
    explicit = override_path or os.getenv("SPEECH_CONFIG")
    root_cfg = load_agent_config(explicit)
    section = require_dict_section(root_cfg, "speech")
    return deepcopy(section)
