from __future__ import annotations
import os
from copy import deepcopy
from typing import Any, Dict
from modules.config_center.agent_yaml_loader import load_agent_config, require_dict_section


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load speak config from central config/agent.yaml.

    Strict mode: module-local config.yml is not used.
    """
    root_cfg = load_agent_config(override_path)
    section = require_dict_section(root_cfg, "speak")
    return deepcopy(section)
