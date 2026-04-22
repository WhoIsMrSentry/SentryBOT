from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

PIPER_MODELS_SOURCE_URL = "https://docs.gladecore.com/files/piper-voice-models"


def env_path(name: str, default: Path) -> Path:
    value = str(os.getenv(name, "")).strip()
    return Path(value).expanduser() if value else default


def bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def normalize_ollama_chat_endpoint(tags_endpoint: str) -> str:
    tags = str(tags_endpoint or "").strip().rstrip("/")
    if tags.endswith("/api/tags"):
        return tags[:-9] + "/api/chat"
    if tags.endswith("/tags"):
        return tags[:-5] + "/chat"
    return tags + "/api/chat"


class RuntimeConfig(BaseModel):
    tts_root: str
    piper_root: str
    xtts_root: str
    piper_bin: str
    xtts_bin: str
    bootstrap_on_start: bool = True
    bootstrap_force: bool = False
    bootstrap_install_piper: bool = True
    bootstrap_install_xtts: bool = True
    bootstrap_download_piper_models: bool = True
    piper_models_source_url: str = PIPER_MODELS_SOURCE_URL
    bootstrap_timeout_sec: float = 300.0
    ollama_tags_endpoint: str
    ollama_chat_endpoint: str
    ollama_timeout_sec: float = 15.0


def load_runtime_config() -> RuntimeConfig:
    base_dir = Path(__file__).resolve().parent.parent
    default_tts_root = base_dir / "runtime"
    default_piper_root = default_tts_root / "piper_models"
    default_xtts_root = default_tts_root / "xtts"

    cfg = RuntimeConfig(
        tts_root=str(env_path("SENTRYBOT_TTS_ROOT", default_tts_root)),
        piper_root=str(env_path("SENTRYBOT_PIPER_ROOT", default_piper_root)),
        xtts_root=str(env_path("SENTRYBOT_XTTS_ROOT", default_xtts_root)),
        piper_bin=str(os.getenv("SENTRYBOT_PIPER_BIN", "piper")).strip() or "piper",
        xtts_bin=str(os.getenv("SENTRYBOT_XTTS_BIN", "tts")).strip() or "tts",
        bootstrap_on_start=bool_env("SENTRYBOT_BOOTSTRAP_ON_START", True),
        bootstrap_force=bool_env("SENTRYBOT_BOOTSTRAP_FORCE", False),
        bootstrap_install_piper=bool_env("SENTRYBOT_BOOTSTRAP_INSTALL_PIPER", True),
        bootstrap_install_xtts=bool_env("SENTRYBOT_BOOTSTRAP_INSTALL_XTTS", True),
        bootstrap_download_piper_models=bool_env("SENTRYBOT_BOOTSTRAP_DOWNLOAD_PIPER_MODELS", True),
        piper_models_source_url=str(
            os.getenv("SENTRYBOT_PIPER_MODELS_SOURCE_URL", PIPER_MODELS_SOURCE_URL)
        ).strip()
        or PIPER_MODELS_SOURCE_URL,
        bootstrap_timeout_sec=float(os.getenv("SENTRYBOT_BOOTSTRAP_TIMEOUT", "300")),
        ollama_tags_endpoint=str(
            os.getenv("SENTRYBOT_OLLAMA_TAGS_ENDPOINT", "https://localhost:5000/api/tags")
        ).strip(),
        ollama_chat_endpoint="",
        ollama_timeout_sec=float(os.getenv("SENTRYBOT_OLLAMA_TIMEOUT", "15")),
    )
    cfg.ollama_chat_endpoint = normalize_ollama_chat_endpoint(cfg.ollama_tags_endpoint)
    return cfg
