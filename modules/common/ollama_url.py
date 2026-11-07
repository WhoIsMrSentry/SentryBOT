"""Canonical Ollama URL normalization helpers (consolidation #6).

Single source of truth for the ``batch06`` helper family that was
copy-pasted across agent_core/vlm_bridge/ai_provider/gateway
config_loaders during earlier patch batches:

- default_ollama_base_url()   safe fallback daemon address
- unwrap_url(value)           strip whitespace/markdown link wrapping
- is_bad_ollama_url(value)    gateway/self-referential URLs are unusable
- normalize_ollama_url(value) unwrap -> bad? default : rstrip('/')
- ensure_ollama_host_env()    seed OLLAMA_HOST/* env from first non-empty

Behavior is byte-equivalent to the deleted per-file copies.
"""

from __future__ import annotations

import os


DEFAULT_LOCAL_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_REMOTE_OLLAMA_URL = "http://whoismrsentry.local:11434"


def default_ollama_base_url() -> str:
    return DEFAULT_LOCAL_OLLAMA_URL


def unwrap_url(value):
    value = str(value or "").strip().replace("\r", "").replace("\n", "").rstrip("/")
    if value.startswith("[") and "](" in value:
        value = value[1:].split("]", 1)[0].strip().rstrip("/")
    return value


_GATEWAY_OLLAMA_EXACT = frozenset({
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://0.0.0.0:8080",
})

_GATEWAY_OLLAMA_PREFIXES = (
    "http://127.0.0.1:8080/",
    "http://localhost:8080/",
    "http://0.0.0.0:8080/",
)


def is_bad_ollama_url(value):
    value = unwrap_url(value)
    lowered = value.lower()

    if not value or value in {"http:", "https:", "http:/", "https:/"}:
        return True

    if "@gateway" in lowered:
        return True

    if lowered in _GATEWAY_OLLAMA_EXACT:
        return True

    if lowered.startswith(_GATEWAY_OLLAMA_PREFIXES):
        return True

    if lowered.endswith(("/ollama", "/ollama/chat")):
        return True

    return False


def normalize_ollama_url(value):
    value = unwrap_url(value)
    if is_bad_ollama_url(value):
        return default_ollama_base_url()
    return value.rstrip("/")


def _seed_ollama_host_env(base_url: str, *, set_sentrybot_url: bool) -> None:
    normalized = unwrap_url(base_url)
    if not normalized:
        return
    os.environ["OLLAMA_HOST"] = normalized
    os.environ["OLLAMA_BASE_URL"] = normalized
    os.environ.setdefault("SENTRYBOT_OLLAMA_BASE_URL", normalized)
    os.environ.setdefault("SENTRYBOT_REMOTE_OLLAMA_URL", normalized)
    if set_sentrybot_url:
        os.environ.setdefault("SENTRYBOT_OLLAMA_URL", normalized)


def ensure_ollama_host_env(
    default: str = DEFAULT_REMOTE_OLLAMA_URL,
) -> None:
    """Seed OLLAMA_HOST / OLLAMA_BASE_URL style env vars from first set."""
    base_url = (
        os.environ.get("OLLAMA_HOST")
        or os.environ.get("SENTRYBOT_OLLAMA_BASE_URL")
        or os.environ.get("SENTRYBOT_REMOTE_OLLAMA_URL")
        or os.environ.get("SENTRYBOT_OLLAMA_URL")
        or default
    )
    if base_url:
        _seed_ollama_host_env(str(base_url), set_sentrybot_url=True)


def ensure_sentrybot_ollama_host_env() -> None:
    """Variant used by gateway agent binding: SENTRYBOT_* env vars take
    priority over OLLAMA_HOST and SENTRYBOT_OLLAMA_URL is not overwritten."""
    base_url = (
        os.environ.get("SENTRYBOT_OLLAMA_BASE_URL")
        or os.environ.get("SENTRYBOT_REMOTE_OLLAMA_URL")
        or os.environ.get("SENTRYBOT_OLLAMA_URL")
        or os.environ.get("OLLAMA_HOST")
        or DEFAULT_REMOTE_OLLAMA_URL
    )
    _seed_ollama_host_env(str(base_url), set_sentrybot_url=False)


__all__ = [
    "DEFAULT_LOCAL_OLLAMA_URL",
    "DEFAULT_REMOTE_OLLAMA_URL",
    "default_ollama_base_url",
    "unwrap_url",
    "is_bad_ollama_url",
    "normalize_ollama_url",
    "ensure_ollama_host_env",
    "ensure_sentrybot_ollama_host_env",
]
