from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from modules.common.config_loader import load_agent_config, require_dict_section
from modules.common.model_policy import get_model_policy, set_required_model
from modules.common.ollama_url import (
    default_ollama_base_url,
    is_bad_ollama_url,
    normalize_ollama_url,
)


# Set required model globally (enforced by model_policy when strict mode enabled)
_REQUIRED_OLLAMA_MODEL = "qwen3.5:9b"
set_required_model(_REQUIRED_OLLAMA_MODEL)


def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _required_model() -> str:
    return _REQUIRED_OLLAMA_MODEL


def _read_declared_models_from_file(path_value: Any) -> list[tuple[str, str]]:
    """Read agent.model / llm.model straight from a config file on disk.

    Strict qwen3.5:9b policy applies only to Ollama configs; Google AI Studio
    configs may use their own model names.
    """
    if not path_value:
        return []
    try:
        path = Path(path_value)
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        if not isinstance(data, dict):
            return []

        agent_cfg = data.get("agent")
        llm_cfg = data.get("llm")

        provider = "ollama"
        if isinstance(llm_cfg, dict) and llm_cfg.get("provider"):
            provider = str(llm_cfg.get("provider")).strip().lower()
        if provider and provider != "ollama":
            return []

        found: list[tuple[str, str]] = []
        if isinstance(agent_cfg, dict) and agent_cfg.get("model"):
            found.append(("agent.model", str(agent_cfg.get("model")).strip()))
        if isinstance(llm_cfg, dict) and llm_cfg.get("model"):
            found.append(("llm.model", str(llm_cfg.get("model")).strip()))
        return found
    except Exception:
        return []


def _raise_if_bad_model(model: Any, source: str) -> None:
    required = _required_model()
    model = str(model or "").strip()
    if model and model != required:
        raise ValueError(f"{source} must be {required}, got {model}")


def _enforce_strict_models(cfg: Dict[str, Any]) -> None:
    llm_cfg = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    provider = "ollama"
    if isinstance(llm_cfg, dict) and llm_cfg.get("provider"):
        provider = str(llm_cfg.get("provider")).strip().lower()
    if provider not in {"", "ollama"}:
        return
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    if isinstance(agent_cfg, dict):
        _raise_if_bad_model(agent_cfg.get("model"), "agent.model")
    if isinstance(llm_cfg, dict):
        _raise_if_bad_model(llm_cfg.get("model"), "llm.model")


def _apply_ollama_url_guard(cfg: Dict[str, Any]) -> None:
    """Single-pass URL guard: pick the first usable Ollama URL among the
    known config locations and write it back to both canonical spots."""
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    ollama_cfg = cfg.get("ollama") if isinstance(cfg.get("ollama"), dict) else {}

    candidates = [
        ollama_cfg.get("base_url"),
        ollama_cfg.get("url"),
        agent_cfg.get("ollama_base_url"),
        agent_cfg.get("base_url"),
        agent_cfg.get("ollama_url"),
    ]

    selected = next(
        (c for c in candidates if c and not is_bad_ollama_url(c)),
        default_ollama_base_url(),
    )
    normalized = normalize_ollama_url(selected)

    ollama_cfg["base_url"] = normalized
    cfg["ollama"] = ollama_cfg
    if isinstance(agent_cfg, dict):
        agent_cfg["ollama_base_url"] = normalized
        cfg["agent"] = agent_cfg


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    """Load agent_core config using centralized model policy."""
    for source, model in _read_declared_models_from_file(path):
        _raise_if_bad_model(model, source)

    cfg = load_agent_config(path)

    if not isinstance(cfg.get("tri_layer", {}), dict):
        cfg["tri_layer"] = {}
    if not isinstance(cfg.get("safety", {}), dict):
        cfg["safety"] = {}

    # Use centralized model policy for provider/model resolution
    policy = get_model_policy()
    provider_config = policy.get_provider_config(cfg)

    # Merge provider config into main config
    for key, value in provider_config.items():
        if key not in cfg:
            cfg[key] = value

    # Ensure single_model_mode and other llm settings are present (for backward compatibility)
    llm_cfg = cfg.get("llm", {})
    if not isinstance(llm_cfg, dict):
        llm_cfg = {}
    llm_cfg.setdefault("single_model_mode", True)
    llm_cfg.setdefault("clm_fallback_enabled", False)
    llm_cfg.setdefault("fallback_on_missing_model", False)
    llm_cfg.setdefault("fallback_on_error", False)
    cfg["llm"] = llm_cfg

    # Ensure agent section has model and request_timeout
    agent_cfg = cfg.get("agent", {})
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}
    agent_cfg.setdefault("model", provider_config.get("model", "qwen3.5:9b"))
    agent_cfg.setdefault("request_timeout", provider_config.get("request_timeout", 60.0))
    cfg["agent"] = agent_cfg

    # Ensure ollama section has base_url (for backward compatibility)
    ollama_cfg = cfg.get("ollama", {})
    if not isinstance(ollama_cfg, dict):
        ollama_cfg = {}
    ollama_cfg.setdefault("base_url", provider_config.get("ollama", {}).get("base_url", "http:"))
    ollama_cfg.setdefault("model", provider_config.get("model", "qwen3.5:9b"))
    ollama_cfg.setdefault("request_timeout", provider_config.get("request_timeout", 60.0))
    cfg["ollama"] = ollama_cfg

    # Former batch06d/e guards, consolidated as direct passes:
    _apply_ollama_url_guard(cfg)
    _enforce_strict_models(cfg)

    # Ensure tri_layer and safety sections exist
    if not isinstance(cfg.get("tri_layer", {}), dict):
        cfg["tri_layer"] = {}
    if not isinstance(cfg.get("safety", {}), dict):
        cfg["safety"] = {}

    return cfg
