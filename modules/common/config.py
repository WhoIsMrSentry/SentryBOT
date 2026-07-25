"""Unified configuration system for SentryBOT.

Provides Pydantic-based config models with YAML loading, environment variable
override, validation, and type-safe access.

Usage:
    from modules.common.config import load_config, ModuleConfig, get_config
    
    # Load module config
    cfg = load_config("modules/neopixel/config/config.yml", NeopixelConfig)
    
    # Or get global config (loads from config/agent.yaml)
    cfg = get_config()
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Type, TypeVar, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _PYDANTIC_SETTINGS_AVAILABLE = True
except ImportError:
    _PYDANTIC_SETTINGS_AVAILABLE = False
    # Fallback BaseSettings for environments without pydantic_settings
    class BaseSettings:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class SettingsConfigDict:  # type: ignore
        def __init__(self, **kwargs):
            pass

T = TypeVar("T", bound="BaseConfig")


class BaseConfig(BaseModel):
    """Base configuration model with common utilities."""
    
    model_config = {
        "extra": "allow",  # Allow extra fields for forward compatibility
        "validate_assignment": True,
    }
    
    @classmethod
    def from_yaml(cls: Type[T], path: str | Path, overrides: dict | None = None) -> T:
        """Load config from YAML file with optional overrides."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if overrides:
            data = deep_merge(data, overrides)
        
        return cls(**data)
    
    @classmethod
    def from_dict(cls: Type[T], data: dict, overrides: dict | None = None) -> T:
        """Create config from dict with optional overrides."""
        if overrides:
            data = deep_merge(data.copy(), overrides)
        return cls(**data)
    
    def to_yaml(self, path: str | Path) -> None:
        """Save config to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(mode="python"), f, allow_unicode=True, sort_keys=False)


class GlobalSettings(BaseSettings):
    """Global settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Core
    robot_name: str = "SentryBOT"
    log_level: str = "INFO"
    data_dir: str = "/data/sentrybot"
    
    # Network
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8080
    gateway_api_key: str = ""
    gateway_admin_key: str = ""
    
    # Hardware
    arduino_port: str = ""
    arduino_baud: int = 115200
    i2c_bus: int = 1
    
    # Audio
    alsa_input_device: str = "default"
    alsa_output_device: str = "default"
    sample_rate: int = 16000
    channels: int = 2
    
    # LLM
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    google_api_key: str = ""
    
    # Paths
    model_cache_dir: str = "/data/models"
    face_db_path: str = "/data/sentrybot/faces"
    
    # Feature flags
    enable_vlm: bool = True
    enable_autonomy: bool = True
    enable_oled: bool = True
    enable_neopixel: bool = True
    enable_speech: bool = True
    enable_speak: bool = True


# Global config cache
_global_config_cache: dict[str, BaseConfig] = {}
_config_lock = threading.Lock()


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml_config(path: str | Path) -> dict:
    """Load YAML config file."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_module_config(
    module_name: str,
    config_class: Type[T],
    base_dir: str | Path | None = None,
    overrides: dict | None = None,
) -> T:
    """Load a module's config from its standard location.
    
    Looks for: {base_dir}/modules/{module_name}/config/config.yml
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent  # repo root
    else:
        base_dir = Path(base_dir)
    
    config_path = base_dir / "modules" / module_name / "config" / "config.yml"
    
    if not config_path.exists():
        # Try alternative: {base_dir}/config/{module_name}.yml
        alt_path = base_dir / "config" / f"{module_name}.yml"
        if alt_path.exists():
            config_path = alt_path
        else:
            raise FileNotFoundError(f"Config not found for module {module_name}: {config_path}")
    
    data = load_yaml_config(config_path)
    if overrides:
        data = deep_merge(data, overrides)
    
    return config_class(**data)


def get_global_settings() -> GlobalSettings:
    """Get global settings from environment."""
    return GlobalSettings()  # type: ignore


# Config registry for hot-reload support
_config_registry: dict[str, tuple[BaseConfig, Path, float]] = {}  # name -> (config, path, mtime)


def register_config(name: str, config: BaseConfig, path: Path) -> None:
    """Register a config for hot-reload monitoring."""
    _config_registry[name] = (config, path, path.stat().st_mtime if path.exists() else 0)


def check_config_changes() -> list[str]:
    """Check registered configs for file changes. Returns list of changed config names."""
    changed = []
    for name, (config, path, mtime) in _config_registry.items():
        if path.exists():
            current_mtime = path.stat().st_mtime
            if current_mtime > mtime:
                changed.append(name)
                _config_registry[name] = (config, path, current_mtime)
    return changed


def reload_config(name: str, config_class: Type[T]) -> T:
    """Reload a registered config from disk."""
    if name not in _config_registry:
        raise KeyError(f"Config not registered: {name}")
    
    old_config, path, _ = _config_registry[name]
    new_config = config_class.from_yaml(path)
    _config_registry[name] = (new_config, path, path.stat().st_mtime)
    return new_config


__all__ = [
    "BaseConfig",
    "GlobalSettings",
    "load_yaml_config",
    "load_module_config",
    "get_global_settings",
    "register_config",
    "check_config_changes",
    "reload_config",
    "deep_merge",
]