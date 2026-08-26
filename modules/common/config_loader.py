"""Unified config loader for SentryBOT.

This module provides the single source of truth for loading and merging
agent.yaml configuration. It combines functionality from:
- ai_provider/config_loader.py (Ollama/Google provider config)
- system_control/config_center/agent_yaml_loader.py (core YAML loading)

All modules should use: `from modules.common.config_loader import load_agent_config`
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, List

import yaml

logger = logging.getLogger("common.config_loader")

# =============================================================================
# Constants
# =============================================================================

_REQUIRED_MODEL = "qwen3.5:9b"
_GOOGLE_PROVIDERS = frozenset({"google", "google_ai_studio", "gemini"})

# Default Gemini model for Google AI Studio (from gemini_model.py)
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"

_DEFAULT_CFG: Dict[str, Any] = {
    "server": {"host": "0.0.0.0", "port": 8099},
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

_LOOPBACK_PREFIXES = (
    "http://localhost:",
    "http://127.0.0.1:",
    "http://0.0.0.0:",
)
_GATEWAY_PATH_RE = re.compile(r"^@gateway(?=/|$)")

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
    """Overlay runtime auth tokens from environment onto config."""
    source = env if env is not None else os.environ
    for env_name, keys in _ENV_PATHS:
        value = str(source.get(env_name, "") or "").strip()
        if not value:
            continue
        parent = _ensure_path(cfg, keys)
        parent[keys[-1]] = value
    return cfg


# =============================================================================
# Google API Key Resolution
# =============================================================================

def _sanitize_google_api_key(raw: Any) -> str:
    """Sanitize and validate Google API key."""
    if not raw:
        return ""
    key = str(raw).strip()
    # Remove common prefixes/suffixes
    key = key.strip('"\'')
    return key


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
                "runtime_profile uses Google but no API key found â€” set google_ai_studio.api_key "
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


# =============================================================================
# URL Helpers (from gateway/url.py)
# =============================================================================

def gateway_base_from_agent_cfg(cfg: Mapping[str, Any], *, port: int = 8080) -> str:
    """Read gateway base from an already-loaded agent.yaml mapping (no reload)."""
    actions = cfg.get("actions", {}) if isinstance(cfg.get("actions", {}), dict) else {}
    explicit = str(actions.get("gateway_base_url", "") or "").strip().rstrip("/")
    if explicit:
        return explicit

    for section in ("gateway", "server"):
        block = cfg.get(section, {})
        if isinstance(block, dict):
            try:
                port = int(block.get("port", port))
            except (TypeError, ValueError):
                pass
            host = str(block.get("host", "127.0.0.1") or "127.0.0.1").strip()
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            return f"http://{host}:{int(port)}"

    return f"http://127.0.0.1:{int(port)}"


def resolve_gateway_base_url(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    port: int = 8080,
    started: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve the gateway base URL from various sources."""
    if started is not None:
        explicit = str(started.get("gateway_base_url", "") or "").strip().rstrip("/")
        if explicit:
            return explicit

    env = str(os.environ.get("SENTRY_GATEWAY_URL", "") or "").strip().rstrip("/")
    if env:
        return env

    if cfg is not None:
        explicit = str(cfg.get("gateway_base_url", "") or "").strip().rstrip("/")
        if explicit:
            return explicit
        return gateway_base_from_agent_cfg(cfg, port=port)

    try:
        return gateway_base_from_agent_cfg(load_agent_config())
    except Exception:
        pass

    return f"http://127.0.0.1:{int(port)}"


def gateway_url(base: str, path: str) -> str:
    return f"{str(base).rstrip('/')}/{str(path).lstrip('/')}"


def resolve_config_url(value: str, gateway_base: Optional[str] = None) -> str:
    """Resolve @gateway/... aliases and loopback :8080 URLs to the active gateway base."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    base = str(gateway_base or resolve_gateway_base_url()).rstrip("/")

    if _GATEWAY_PATH_RE.match(raw):
        path = raw[len("@gateway") :]
        return gateway_url(base, path or "/")

    for prefix in _LOOPBACK_PREFIXES:
        if raw.lower().startswith(prefix):
            port_match = re.match(r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d+)", raw.lower())
            if port_match:
                port_num = int(port_match.group(1))
                if port_num not in (8080, 8000):
                    return raw
            suffix = raw.split(":", 2)[-1]
            if "/" in suffix:
                path = "/" + suffix.split("/", 1)[1]
            else:
                path = ""
            return gateway_url(base, path)
    return raw


def rewrite_loopback_urls(obj: Any, gateway_base: str) -> Any:
    """Recursively rewrite @gateway/ and loopback :8080 URLs in nested config dicts."""
    base = str(gateway_base or "").rstrip("/")
    if isinstance(obj, str):
        return resolve_config_url(obj, base)
    if isinstance(obj, dict):
        return {k: rewrite_loopback_urls(v, base) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite_loopback_urls(v, base) for v in obj]
    return obj


def patch_service_endpoints(endpoints: Dict[str, Any], gateway_base: str) -> Dict[str, Any]:
    """Rewrite autonomy-style endpoint map to use a single gateway base."""
    base = str(gateway_base or "").rstrip("/")
    if not base:
        return endpoints

    service_paths = {
        "arduino": "/arduino",
        "neopixel": "/neopixel",
        "speak": "/speak",
        "ollama": "/ollama",
        "speech": "/speech",
        "interactions": "/interactions",
        "oled_faces": "/oled_faces",
        "state_manager": "/state",
        "animate": "/animate",
        "vlm": "/vlm",
        "vision": "/vlm",
        "camera": "/camera",
        "notifier": "/notify",
        "autonomy": "/autonomy",
        "agent_core": "/agent",
        "expression": "/expression",
    }

    out = dict(endpoints or {})
    for key, path_suffix in service_paths.items():
        out[key] = f"{base}{path_suffix}"
    return out


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

    Delegates to ``modules.common.ollama_url`` â€” the consolidated batch06
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
    service_cfg = require_dict_section(root_cfg, "ai_provider")  # renamed from ollama_service
    google_global = root_cfg.get("google_ai_studio", {})
    if not isinstance(google_global, dict):
        google_global = {}

    provider = str(llm_cfg.get("provider", "")).strip().lower() or "ollama"
    request_timeout = _to_float(
        ollama_global.get("request_timeout", agent_cfg.get("request_timeout", 60.0)),
        60.0,
    )

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
                    agent_cfg.get("ollama_base_url")
                    or ollama_global.get("base_url")
                    or os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
                    or os.getenv("OLLAMA_BASE_URL")
                    or os.getenv("AGENT_OLLAMA_BASE_URL")
                    or "http:"
                ),
                "model": _REQUIRED_MODEL,
                "request_timeout": request_timeout,
            },
        }
    else:
        model = _pick_model(agent_cfg, llm_cfg, ollama_global)
        if model != _REQUIRED_MODEL:
            raise ValueError(
                f"Ollama profile requires model '{_REQUIRED_MODEL}', got '{model or '<empty>'}'"
            )

        base_url = _normalize_base_url(
            agent_cfg.get("ollama_base_url")
            or llm_cfg.get("base_url")
            or ollama_global.get("base_url")
            or os.getenv("SENTRYBOT_OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("AGENT_OLLAMA_BASE_URL")
            or "http:"
        )
        if not base_url:
            raise ValueError("agent.ollama_base_url is required")

        core_cfg = {
            "llm": {
                "provider": "ollama",
                "single_model_mode": True,
                "model": _REQUIRED_MODEL,
                "primary_model": _REQUIRED_MODEL,
                "base_url": base_url,
            },
            "ollama": {
                "base_url": base_url,
                "model": _REQUIRED_MODEL,
                "request_timeout": request_timeout,
            },
            "google_ai_studio": google_global,
        }

    merged = deep_merge(_DEFAULT_CFG, service_cfg)
    merged = deep_merge(merged, core_cfg)

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

    return merged


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

def load_agent_config(explicit_path: Optional[str | os.PathLike[str]] = None) -> Dict[str, Any]:
    """Load and fully process agent.yaml with all overlays.

    This is the main entry point for all modules needing the full config.
    """
    cfg_path = resolve_agent_cfg_path(explicit_path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"agent.yaml must be a mapping at top-level: {cfg_path}")

    load_dotenv()
    cfg = apply_runtime_profile(raw)
    cfg = inject_google_api_key(cfg)
    cfg = inject_runtime_secrets(cfg)
    base = gateway_base_from_agent_cfg(cfg)
    return rewrite_loopback_urls(cfg, base)


# =============================================================================
# Public API
# =============================================================================

# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Main entry points
    "load_agent_config",
    "load_ai_provider_config",
    "resolve_agent_cfg_path",
    # YAML utilities
    "deep_merge",
    "require_dict_section",
    "apply_runtime_profile",
    # Environment & secrets
    "load_dotenv",
    "inject_runtime_secrets",
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
    # Provider config
    "load_ai_provider_config",
    # Runtime profile
    "apply_runtime_profile",
    "list_runtime_profiles",
    "active_runtime_profile",
    # Constants
    "_REQUIRED_MODEL",
    "_GOOGLE_PROVIDERS",
    "_DEFAULT_CFG",
    "DEFAULT_GEMINI_MODEL",
]
