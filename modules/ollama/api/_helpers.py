from __future__ import annotations
import os
from typing import Optional


def persona_dir(cfg: dict, name: Optional[str] = None) -> str:
    pdir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    pname = name or str(cfg.get("persona", {}).get("default", "sentry"))
    return os.path.join(pdir, pname)


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
