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


def default_ollama_base_url() -> str:
    return "http" + "://127.0.0.1:11434"


def unwrap_url(value):
    value = str(value or "").strip().replace("\r", "").replace("\n", "").rstrip("/")
    if value.startswith("[") and "](" in value:
        value = value[1:].split("]", 1)[0].strip().rstrip("/")
    return value


def is_bad_ollama_url(value):
    value = unwrap_url(value)
    lowered = value.lower()

    if not value or value in {"http:", "https:", "http:/", "https:/"}:
        return True

    if "@gateway" in lowered:
        return True

    if lowered in {
        "http" + "://127.0.0.1:8080",
        "http" + "://localhost:8080",
        "http" + "://0.0.0.0:8080",
    }:
        return True

    if lowered.startswith(("http" + "://127.0.0.1:8080/").lower()):
        return True

    if lowered.startswith(("http" + "://localhost:8080/").lower()):
        return True

    if lowered.startswith(("http" + "://0.0.0.0:8080/").lower()):
        return True

    if lowered.endswith("/ollama") or lowered.endswith("/ollama/chat"):
        return True

    return False


def normalize_ollama_url(value):
    value = unwrap_url(value)
    if is_bad_ollama_url(value):
        return default_ollama_base_url()
    return value.rstrip("/")


def ensure_ollama_host_env(
    default: str = "http://whoismrsentry.local:11434",
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
        base_url = str(base_url).rstrip("/")
        os.environ["OLLAMA_HOST"] = base_url
        os.environ["OLLAMA_BASE_URL"] = base_url
        os.environ.setdefault("SENTRYBOT_OLLAMA_BASE_URL", base_url)
        os.environ.setdefault("SENTRYBOT_REMOTE_OLLAMA_URL", base_url)
        os.environ.setdefault("SENTRYBOT_OLLAMA_URL", base_url)


def ensure_sentrybot_ollama_host_env() -> None:
    """Variant used by gateway agent binding: SENTRYBOT_* env vars take
    priority over OLLAMA_HOST and SENTRYBOT_OLLAMA_URL is not overwritten."""
    base_url = (
        os.environ.get("SENTRYBOT_OLLAMA_BASE_URL")
        or os.environ.get("SENTRYBOT_REMOTE_OLLAMA_URL")
        or os.environ.get("SENTRYBOT_OLLAMA_URL")
        or os.environ.get("OLLAMA_HOST")
        or "http://whoismrsentry.local:11434"
    )
    base_url = str(base_url).strip().rstrip("/")
    if base_url:
        os.environ["OLLAMA_HOST"] = base_url
        os.environ["OLLAMA_BASE_URL"] = base_url
        os.environ.setdefault("SENTRYBOT_OLLAMA_BASE_URL", base_url)
        os.environ.setdefault("SENTRYBOT_REMOTE_OLLAMA_URL", base_url)


__all__ = [
    "default_ollama_base_url",
    "unwrap_url",
    "is_bad_ollama_url",
    "normalize_ollama_url",
    "ensure_ollama_host_env",
    "ensure_sentrybot_ollama_host_env",
]
