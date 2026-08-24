from __future__ import annotations
import os
from copy import deepcopy
from typing import Any, Dict
from modules.common.config_loader import load_agent_config, require_dict_section
from modules.voice.audio_router import AudioConfig, AudioRouterConfig


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


def load_audio_router_config() -> AudioRouterConfig:
    """Load audio_router configuration from agent.yaml."""
    root_cfg = load_agent_config()
    audio_router_cfg = root_cfg.get("audio_router")
    if isinstance(audio_router_cfg, dict):
        capture_cfg = audio_router_cfg.get("capture", {})
        return AudioRouterConfig(
            capture=AudioConfig(
                device=capture_cfg.get("device", "default"),
                sample_rate=capture_cfg.get("sample_rate", 16000),
                channels=capture_cfg.get("channels", 2),
                frame_size=capture_cfg.get("frame_size", 1024),
                format=capture_cfg.get("format", "int16"),
                vad_enabled=capture_cfg.get("vad_enabled", True),
                vad_threshold=capture_cfg.get("vad_threshold", 0.01),
            )
        )
    return AudioRouterConfig()
