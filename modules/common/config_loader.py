"""Unified config loader for SentryBOT.

This module provides the single source of truth for loading and merging
agent.yaml configuration. It combines functionality from:
- ai_provider/config_loader.py (Ollama/Google provider config)
- system_control/config_center/agent_yaml_loader.py (core YAML loading)

All modules should use: `from modules.common.config_loader import load_agent_config`
"""

from __future__ import annotations

import copy
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from .url_utils import (
    gateway_base_from_agent_cfg,
    gateway_url,
    patch_service_endpoints,
    resolve_config_url,
    resolve_gateway_base_url,
    rewrite_loopback_urls,
)

logger = logging.getLogger("common.config_loader")

# =============================================================================
# Constants
# =============================================================================

from modules.common.model_roles import DEFAULT_CHAT_MODEL

_REQUIRED_MODEL = DEFAULT_CHAT_MODEL
_GOOGLE_PROVIDERS = frozenset({"google", "google_ai_studio", "gemini"})

# Default Gemini model for Google AI Studio (from gemini_model.py)
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"

_DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8099},
    "llm": {"provider": "ollama", "single_model_mode": True},
    "ollama": {"base_url": "http://whoismrsentry.local:11434", "model": _REQUIRED_MODEL, "request_timeout": 60.0},
    "google_ai_studio": {
        "api_key": "",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 45.0,
    },
    "persona": {"default": "sentry", "dir": "modules/ai_provider/config/personalities"},
    "actions": {
        "endpoint": "http://localhost:8080/autonomy/apply_actions",
        "default_apply": True,
        "timeout": 1.5,
    },
    "translation": {
        "enabled": True,
        "default_source_lang": "tr",
        "model": "",
        "cache_size": 128,
    },
}

_PROFILE_SECTION_KEYS: Tuple[str, ...] = (
    "agent",
    "llm",
    "ollama",
    "google_ai_studio",
    "ollama_service",
    "vlm_bridge",
    "arduino_serial",
    "esp_link",
    "speak",
    "speech",
    "tri_layer",
    "realtime_profile",
    "safety",
)

_ENV_PATHS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("SENTRYBOT_AGENT_AUTH_TOKEN", ("agent", "auth_token")),
    ("SENTRYBOT_VLM_AUTH_TOKEN", ("vlm_bridge", "remote", "auth_token")),
    ("SENTRYBOT_VLM_AUTH_TOKEN", ("vlm_bridge", "remote_multimodal", "auth_token")),
    ("SENTRYBOT_TTS_AUTH_TOKEN", ("speak", "tts", "remote", "auth_token")),
)

# =============================================================================
# Path Resolution
# =============================================================================

def _repo_root() -> Path:
    """Return repository root (2 parents up from this file)."""
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
    """Resolve the path to agent.yaml, checking multiple locations."""
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


# =============================================================================
# YAML Loading & Merging
# =============================================================================

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base, preserving nested dicts."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(dict(out[key]), value)
        else:
            out[key] = value
    return out


def require_dict_section(cfg: Dict[str, Any], section: str) -> Dict[str, Any]:
    """Extract a required dict section from config, raising if missing/invalid."""
    data = cfg.get(section)
    if not isinstance(data, dict):
        raise KeyError(f"agent.yaml missing required section: {section}")
    return data


def _deep_merge_profile(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge profile patch; do not overwrite with empty strings/null."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_profile(dict(out[key]), value)
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def apply_runtime_profile(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the active runtime profile into *cfg* (in place) and return it."""
    profile_root = cfg.get("runtime_profile")
    if not isinstance(profile_root, dict):
        return cfg

    active = str(profile_root.get("active", "")).strip()
    profiles = profile_root.get("profiles")
    if not active or not isinstance(profiles, dict):
        return cfg

    patch = profiles.get(active)
    if not isinstance(patch, dict):
        return cfg

    for key in _PROFILE_SECTION_KEYS:
        section_patch = patch.get(key)
        if not isinstance(section_patch, dict):
            continue
        existing = cfg.get(key)
        if isinstance(existing, dict):
            cfg[key] = _deep_merge_profile(dict(existing), section_patch)
        else:
            cfg[key] = dict(section_patch)

    cfg["_runtime_profile_active"] = active
    return cfg


# =============================================================================
# Environment & Secrets
# =============================================================================

def load_dotenv(path: Path | None = None) -> None:
    """Load .env file into os.environ (if not already set)."""
    if path is None and (os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules):
        return
    target = path or (_repo_root() / ".env")
    if not target.exists():
        return
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _ensure_path(cfg: Dict[str, Any], keys: Tuple[str, ...]) -> Dict[str, Any]:
    cur: Dict[str, Any] = cfg
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    return cur


def inject_runtime_secrets(cfg: Dict[str, Any], env: Mapping[str, str] | None = None) -> Dict[str, Any]:
    """Overlay runtime auth tokens and explicit URL overrides from env onto config."""
    from .ollama_url import resolve_env_ollama_base_url

    source = env if env is not None else os.environ
    for env_name, keys in _ENV_PATHS:
        value = str(source.get(env_name, "") or "").strip()
        if not value:
            continue
        parent = _ensure_path(cfg, keys)
        parent[keys[-1]] = value

    env_ollama_url = resolve_env_ollama_base_url(source)
    if env_ollama_url:
        for keys in (
            ("ollama", "base_url"),
            ("agent", "ollama_base_url"),
            ("vlm_bridge", "vision_llm", "base_url"),
            ("google_ai_studio", "vision_llm", "base_url"),
        ):
            parent = _ensure_path(cfg, keys)
            parent[keys[-1]] = env_ollama_url
    return cfg


# =============================================================================
# Google API Key Resolution
# =============================================================================

_GOOGLE_API_KEY_PLACEHOLDERS = {
    "your-google-api-key",
    "your_google_api_key",
    "your-api-key",
    "changeme",
    "replace_me",
    "replace-with-your-key",
}


def _sanitize_google_api_key(raw: Any) -> str:
    """Sanitize and validate Google API key without circular imports."""
    if not raw:
        return ""
    key = str(raw).strip().strip('"\'')
    lowered = key.lower()
    if lowered in _GOOGLE_API_KEY_PLACEHOLDERS or "your-google-api-key" in lowered:
        return ""
    return key


def deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionary override into base."""
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = deep_update(base[k], v)
        else:
            base[k] = v
    return base


_deep_update = deep_update


def resolve_google_api_key(cfg: Dict[str, Any]) -> str:
    """Resolve Google AI Studio API key from config + environment."""
    google_cfg = cfg.get("google_ai_studio", {})
    if not isinstance(google_cfg, dict):
        google_cfg = {}
    key = _sanitize_google_api_key(google_cfg.get("api_key", ""))
    if not key:
        key = _sanitize_google_api_key(os.getenv("GOOGLE_API_KEY", ""))
    return key


def inject_google_api_key(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Attach resolved Google API key to config without wiping existing valid value."""
    key = resolve_google_api_key(cfg)
    if not key:
        llm = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
        provider = str(llm.get("provider", "")).strip().lower()
        if provider in _GOOGLE_PROVIDERS:
            logger.warning(
                "runtime_profile uses Google but no API key found — set google_ai_studio.api_key "
                "in config/agent.yaml or export GOOGLE_API_KEY before starting the robot"
            )
        return cfg
    google_cfg = cfg.get("google_ai_studio", {})
    if not isinstance(google_cfg, dict):
        google_cfg = {}
    else:
        google_cfg = dict(google_cfg)
    if not _sanitize_google_api_key(google_cfg.get("api_key", "")):
        google_cfg["api_key"] = key
    cfg["google_ai_studio"] = google_cfg
    return cfg


# URL Helpers are imported at module top and re-exported via __all__.


# =============================================================================
# Provider-Specific Config (from ai_provider/config_loader.py)
# =============================================================================

def _to_float(raw: Any, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _pick_model(agent_cfg: Dict[str, Any], llm_cfg: Dict[str, Any], ollama_cfg: Dict[str, Any]) -> str:
    for candidate in (
        agent_cfg.get("model"),
        llm_cfg.get("model"),
        llm_cfg.get("primary_model"),
        ollama_cfg.get("model"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _normalize_base_url(raw: Any) -> str:
    """Normalize an Ollama daemon base URL (canonical single implementation).

    Delegates to ``modules.common.ollama_url`` — the consolidated batch06
    helper family. Explicit valid URLs win; gateway/self URLs and malformed
    values map back to the local daemon.
    """
    from modules.common.ollama_url import normalize_ollama_url

    return normalize_ollama_url(raw)


def load_ai_provider_config(config_path: str | None = None) -> Dict[str, Any]:
    """Load and merge config specifically for ai_provider module."""
    root_cfg = load_agent_config(config_path)

    agent_cfg = require_dict_section(root_cfg, "agent")
    llm_cfg = require_dict_section(root_cfg, "llm")
    ollama_global = require_dict_section(root_cfg, "ollama")
    ollama_service_cfg = root_cfg.get("ollama_service", {})
    if not isinstance(ollama_service_cfg, dict):
        ollama_service_cfg = {}
    ai_provider_cfg = root_cfg.get("ai_provider", {})
    if isinstance(ai_provider_cfg, dict) and ai_provider_cfg:
        service_cfg = deep_merge(ollama_service_cfg, ai_provider_cfg)
    elif ollama_service_cfg:
        service_cfg = ollama_service_cfg
    else:
        service_cfg = require_dict_section(root_cfg, "ollama_service")
    google_global = root_cfg.get("google_ai_studio", {})
    if not isinstance(google_global, dict):
        google_global = {}

    provider = str(llm_cfg.get("provider", "")).strip().lower() or "ollama"
    request_timeout = _to_float(
        ollama_global.get("request_timeout", agent_cfg.get("request_timeout", 60.0)),
        60.0,
    )

    from .ollama_url import resolve_env_ollama_base_url

    env_ollama_url = resolve_env_ollama_base_url()
    if provider in _GOOGLE_PROVIDERS:
        model = (
            str(google_global.get("model", "")).strip()
            or _pick_model(agent_cfg, llm_cfg, ollama_global)
            or "gemini-1.5-flash"
        )
        google_timeout = _to_float(google_global.get("request_timeout", request_timeout), request_timeout)
        core_cfg: Dict[str, Any] = {
            "llm": {
                "provider": "google_ai_studio",
                "single_model_mode": True,
                "model": model,
                "primary_model": model,
            },
            "google_ai_studio": {
                **google_global,
                "model": model,
                "request_timeout": google_timeout,
            },
            "ollama": {
                "base_url": _normalize_base_url(
                    env_ollama_url
                    or agent_cfg.get("ollama_base_url")
                    or ollama_global.get("base_url")
                    or ""
                ),
                "model": _REQUIRED_MODEL,
                "request_timeout": request_timeout,
            },
        }
    else:
        single_model_mode = bool(llm_cfg.get("single_model_mode", True))
        required_model = str(llm_cfg.get("required_model", _REQUIRED_MODEL)).strip() or _REQUIRED_MODEL
        raw_allowed = llm_cfg.get("allowed_models")
        allowed_models = (
            [str(m).strip() for m in raw_allowed if str(m).strip()]
            if isinstance(raw_allowed, (list, tuple))
            else []
        )
        model = _pick_model(agent_cfg, llm_cfg, ollama_global)
        if allowed_models:
            if model not in allowed_models:
                raise ValueError(
                    f"Ollama profile requires model in {allowed_models}, got '{model or '<empty>'}'"
                )
            active_model = model
        elif single_model_mode:
            if model != required_model:
                raise ValueError(
                    f"Ollama profile requires model '{required_model}', got '{model or '<empty>'}'"
                )
            active_model = required_model
        else:
            active_model = model or required_model

        base_url = _normalize_base_url(
            env_ollama_url
            or agent_cfg.get("ollama_base_url")
            or llm_cfg.get("base_url")
            or ollama_global.get("base_url")
            or ""
        )
        if not base_url:
            raise ValueError("agent.ollama_base_url is required")

        core_cfg = {
            "llm": {
                "provider": "ollama",
                "single_model_mode": single_model_mode,
                "required_model": required_model,
                "allowed_models": allowed_models,
                "model": active_model,
                "primary_model": active_model,
                "base_url": base_url,
            },
            "ollama": {
                "base_url": base_url,
                "model": active_model,
                "request_timeout": request_timeout,
            },
            "google_ai_studio": google_global,
        }

    merged = deep_merge(_DEFAULT_CFG, service_cfg)
    merged = deep_merge(merged, core_cfg)

    actions_cfg = merged.get("actions", {})
    if isinstance(actions_cfg, dict) and actions_cfg.get("endpoint"):
        actions_copy = dict(actions_cfg)
        actions_copy["endpoint"] = resolve_config_url(
            str(actions_cfg["endpoint"]),
            resolve_gateway_base_url(root_cfg),
        )
        merged["actions"] = actions_copy

    if provider in _GOOGLE_PROVIDERS:
        trans = merged.get("translation", {})
        if isinstance(trans, dict):
            merged["translation"] = {**trans, "enabled": False}

    google_cfg = merged.get("google_ai_studio", {})
    if isinstance(google_cfg, dict):
        key = str(google_cfg.get("api_key", "")).strip()
        if not key:
            env_key = str(os.getenv("GOOGLE_API_KEY", "")).strip()
            if env_key:
                google_cfg = {**google_cfg, "api_key": env_key}
                merged["google_ai_studio"] = google_cfg

    from modules.common.bind_host import apply_bind_host

    return apply_bind_host(merged, "OLLAMA_SERVICE_HOST")


# =============================================================================
# Runtime Profile Helpers
# =============================================================================

def list_runtime_profiles(cfg: Dict[str, Any]) -> List[str]:
    profile_root = cfg.get("runtime_profile")
    if not isinstance(profile_root, dict):
        return []
    profiles = profile_root.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return sorted(str(name) for name in profiles.keys())


def active_runtime_profile(cfg: Dict[str, Any]) -> str:
    explicit = str(cfg.get("_runtime_profile_active", "")).strip()
    if explicit:
        return explicit
    profile_root = cfg.get("runtime_profile")
    if isinstance(profile_root, dict):
        return str(profile_root.get("active", "")).strip()
    return ""


# =============================================================================
# Main Entry Points
# =============================================================================

_ENV_SIGNATURE_KEYS: Tuple[str, ...] = (
    "AGENT_CFG",
    "GOOGLE_API_KEY",
    "SENTRYBOT_PROFILE",
    "SENTRYBOT_AGENT_AUTH_TOKEN",
    "SENTRYBOT_VLM_AUTH_TOKEN",
    "SENTRYBOT_TTS_AUTH_TOKEN",
    "OLLAMA_BASE_URL",
    "SENTRYBOT_OLLAMA_BASE_URL",
    "AGENT_OLLAMA_BASE_URL",
    "SENTRY_GATEWAY_URL",
)
_AGENT_CFG_CACHE_LOCK = threading.Lock()
_AGENT_CFG_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}


def load_agent_config(explicit_path: Optional[str | os.PathLike[str]] = None) -> Dict[str, Any]:
    """Load and fully process agent.yaml with all overlays.

    This is the main entry point for all modules needing the full config.
    """
    load_dotenv()
    cfg_path = resolve_agent_cfg_path(explicit_path)
    try:
        resolved_str = str(cfg_path.resolve())
        mtime_ns = cfg_path.stat().st_mtime_ns
    except OSError:
        resolved_str = str(cfg_path)
        mtime_ns = 0

    env_signature = tuple((k, os.environ.get(k, "")) for k in _ENV_SIGNATURE_KEYS)
    cache_key = (resolved_str, mtime_ns, env_signature)

    with _AGENT_CFG_CACHE_LOCK:
        cached = _AGENT_CFG_CACHE.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"agent.yaml must be a mapping at top-level: {cfg_path}")

    cfg = apply_runtime_profile(raw)
    cfg = inject_google_api_key(cfg)
    cfg = inject_runtime_secrets(cfg)
    base = gateway_base_from_agent_cfg(cfg)
    final_cfg = rewrite_loopback_urls(cfg, base)

    with _AGENT_CFG_CACHE_LOCK:
        if len(_AGENT_CFG_CACHE) >= 16:
            _AGENT_CFG_CACHE.clear()
        _AGENT_CFG_CACHE[cache_key] = copy.deepcopy(final_cfg)

    return final_cfg


_KEY_IN_URL_RE = re.compile(r"(key=)([^&\s\"']+)", re.IGNORECASE)
_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE)


def redact_secrets(text: object) -> str:
    """Remove API keys and Bearer tokens from log-safe strings."""
    msg = str(text or "")
    msg = _KEY_IN_URL_RE.sub(r"\1***", msg)
    msg = _BEARER_RE.sub(r"\1***", msg)
    return msg


def load_module_config(
    default_path: Path,
    path: Optional[str | os.PathLike[str]] = None,
    *,
    section: Optional[str] = None,
    bind_env: Optional[str] = None,
    resolve_urls: bool = False,
) -> Dict[str, Any]:
    """Load a module-local config.yml with optional agent.yaml merge, URL resolution, and bind host."""
    p = Path(path) if path else default_path
    if not p.exists():
        p = default_path
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    if not isinstance(cfg, dict):
        cfg = {}

    if section:
        try:
            agent_cfg = load_agent_config() or {}
            override = agent_cfg.get(section)
            if isinstance(override, dict) and override:
                base_sec = cfg.get(section, {}) if isinstance(cfg.get(section), dict) else {}
                cfg[section] = deep_merge(base_sec, override)
        except Exception:
            pass

        if resolve_urls and isinstance(cfg.get(section), dict):
            try:
                gw_base = resolve_gateway_base_url()
                cfg[section] = rewrite_loopback_urls(cfg[section], gw_base)
            except Exception:
                pass

        if bind_env and isinstance(cfg.get(section), dict):
            from modules.common.bind_host import apply_bind_host

            cfg[section] = apply_bind_host(cfg[section], bind_env)

    return cfg


def clear_agent_config_cache() -> None:
    """Clear the cached agent.yaml dictionary."""
    with _AGENT_CFG_CACHE_LOCK:
        _AGENT_CFG_CACHE.clear()


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Main entry points
    "load_agent_config",
    "load_ai_provider_config",
    "load_module_config",
    "clear_agent_config_cache",
    "resolve_agent_cfg_path",
    # YAML utilities
    "deep_merge",
    "deep_update",
    "_deep_update",
    "require_dict_section",
    "apply_runtime_profile",
    # Environment & secrets
    "load_dotenv",
    "inject_runtime_secrets",
    "redact_secrets",
    # Google API key
    "resolve_google_api_key",
    "inject_google_api_key",
    # URL helpers
    "resolve_gateway_base_url",
    "gateway_base_from_agent_cfg",
    "gateway_url",
    "resolve_config_url",
    "rewrite_loopback_urls",
    "patch_service_endpoints",
    # Runtime profile
    "list_runtime_profiles",
    "active_runtime_profile",
    # Constants
    "_REQUIRED_MODEL",
    "_GOOGLE_PROVIDERS",
    "_DEFAULT_CFG",
    "DEFAULT_GEMINI_MODEL",
]
