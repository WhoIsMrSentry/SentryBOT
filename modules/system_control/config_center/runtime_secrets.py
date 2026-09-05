"""Overlay runtime auth tokens from environment onto agent.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Mapping

_ENV_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SENTRYBOT_AGENT_AUTH_TOKEN", ("agent", "auth_token")),
    ("SENTRYBOT_VLM_AUTH_TOKEN", ("vlm_bridge", "remote", "auth_token")),
    ("SENTRYBOT_VLM_AUTH_TOKEN", ("vlm_bridge", "remote_multimodal", "auth_token")),
    ("SENTRYBOT_TTS_AUTH_TOKEN", ("speak", "tts", "remote", "auth_token")),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
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


def _ensure_path(cfg: Dict[str, Any], keys: tuple[str, ...]) -> Dict[str, Any]:
    cur: Dict[str, Any] = cfg
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    return cur


def inject_runtime_secrets(cfg: Dict[str, Any], env: Mapping[str, str] | None = None) -> Dict[str, Any]:
    source = env if env is not None else os.environ
    for env_name, keys in _ENV_PATHS:
        value = str(source.get(env_name, "") or "").strip()
        if not value:
            continue
        parent = _ensure_path(cfg, keys)
        parent[keys[-1]] = value
    return cfg
