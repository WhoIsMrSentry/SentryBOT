from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from modules.config_center.agent_yaml_loader import deep_merge, load_agent_config

_DEF_CFG_PATH = Path(__file__).parent / "config" / "config.yml"


def load_config(override_path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load wakeword config.

    Priority:
    1) override_path / WAKEWORD_CONFIG env -> local config.yml
    2) deep-merge config/agent.yaml `wakeword` section (when present)
    3) sync `speech.audio` device from agent.yaml if wakeword audio device unset
    """
    cfg_env = os.getenv("WAKEWORD_CONFIG")
    cfg_path = Path(override_path or cfg_env) if (override_path or cfg_env) else _DEF_CFG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    try:
        agent_cfg = load_agent_config()
        section = agent_cfg.get("wakeword")
        if isinstance(section, dict):
            data = deep_merge(data, section)
        speech_audio = (agent_cfg.get("speech") or {}).get("audio")
        if isinstance(speech_audio, dict):
            audio = data.setdefault("audio", {})
            if isinstance(audio, dict):
                dev = audio.get("device")
                speech_dev = speech_audio.get("device")
                if (not dev or str(dev).strip().lower() in {"", "null", "none"}) and speech_dev:
                    audio["device"] = speech_dev
    except Exception:
        pass

    return data
