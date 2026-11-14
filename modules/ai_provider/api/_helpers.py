from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Optional

DEFAULT_PERSONA_DIR = "modules/ai_provider/config/personalities"
_SAFE_PERSONA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_persona_name(name: Optional[str]) -> str:
    cleaned = str(name or "").strip()
    if not cleaned or not _SAFE_PERSONA_RE.match(cleaned):
        raise ValueError(f"invalid persona name: {name!r}")
    return cleaned


def persona_base_dir(cfg: dict) -> Path:
    raw = str((cfg.get("persona", {}) or {}).get("dir") or DEFAULT_PERSONA_DIR).strip() or DEFAULT_PERSONA_DIR
    return Path(raw).resolve()


def persona_dir(cfg: dict, name: Optional[str] = None) -> str:
    base = persona_base_dir(cfg)
    pname = validate_persona_name(name or (cfg.get("persona", {}) or {}).get("default", "sentry"))
    target = (base / pname).resolve()
    if not target.is_relative_to(base):
        raise ValueError("persona path escapes base directory")
    return str(target)


def load_persona_text(cfg: dict, name: Optional[str] = None) -> str:
    pdir = persona_dir(cfg, name)
    path = os.path.join(pdir, "persona.txt")
    if not os.path.exists(path):
        return "You are a helpful assistant."
    with open(path, "r", encoding="utf-8") as f:
        return "".join([line for line in f if len(line.strip()) > 0 and not line.strip().startswith("#")])


def should_use_persona_model(
    provider_name: str,
    single_model_mode: bool,
    use_persona_models: bool,
) -> bool:
    return (
        str(provider_name or "").strip().lower() == "ollama"
        and not bool(single_model_mode)
        and bool(use_persona_models)
    )
