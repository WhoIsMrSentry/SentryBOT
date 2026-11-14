from __future__ import annotations

import logging
import os
import threading
from typing import Any, List
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
import requests

from modules.ai_provider.api._helpers import (
    DEFAULT_PERSONA_DIR,
    load_persona_text,
    persona_base_dir,
    persona_dir,
    should_use_persona_model,
    validate_persona_name,
)
from modules.ai_provider.services.chat import OllamaChatService

logger = logging.getLogger("ollama.api")
_MAX_PERSONA_BYTES = 256 * 1024


def get_persona_router(
    cfg: dict,
    client: Any,
    provider_name: str,
    single_model_mode: bool,
    use_persona_models: bool,
    ollama_num_predict: int,
    runtime: dict,
) -> APIRouter:
    r = APIRouter(tags=["ollama-persona"])
    rt_lock = runtime.setdefault("_lock", threading.RLock())

    @r.get("/persona")
    def get_persona():
        with rt_lock:
            return {
                "ok": True,
                "active": runtime["active_persona"],
                "persona": runtime["persona_text"][:4096],
            }

    @r.get("/personas")
    def list_personas() -> dict:
        base = persona_base_dir(cfg)
        items: List[str] = []
        if base.exists():
            for entry in sorted(base.iterdir()):
                if entry.is_dir():
                    items.append(entry.name)
        with rt_lock:
            active = runtime["active_persona"]
        return {"ok": True, "items": items, "active": active}

    @r.post("/persona/select")
    def select_persona(name: str):
        try:
            safe_name = validate_persona_name(name)
            pdir = persona_dir(cfg, safe_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        path = os.path.join(pdir, "persona.txt")
        if not os.path.exists(path):
            return {"ok": False, "error": "persona not found"}

        raw_content = load_persona_text(cfg, safe_name)
        if "FROM " in raw_content and "SYSTEM " in raw_content:
            modelfile = raw_content
        else:
            base_model = str(cfg.get("ollama", {}).get("model", "qwen3.5:9b"))
            modelfile = f'FROM {base_model}\nSYSTEM """\n{raw_content}\n"""'

        success = False
        if provider_name == "ollama" and not single_model_mode and use_persona_models:
            success = client.create_model(safe_name, modelfile)
            if not success:
                logger.error("Failed to create model for persona %s", safe_name)
        elif provider_name == "ollama":
            logger.info("Persona model creation disabled (single_model_mode/use_persona_models) for '%s'.", safe_name)

        use_persona_flag = should_use_persona_model(provider_name, single_model_mode, use_persona_models)
        with rt_lock:
            runtime["active_persona"] = safe_name
            runtime["persona_text"] = raw_content
            runtime["_persona_cache"][safe_name] = raw_content
            existing_chat = runtime.get("chat")
            if existing_chat is not None and hasattr(existing_chat, "update_persona"):
                existing_chat.update_persona(safe_name, use_persona_flag)
            else:
                runtime["chat"] = OllamaChatService(
                    client,
                    persona_name=safe_name,
                    max_history=6,
                    use_persona_as_model=use_persona_flag,
                    num_predict=ollama_num_predict,
                )

        return {
            "ok": True,
            "active": safe_name,
            "provider": provider_name,
            "model_created": success if provider_name == "ollama" else None,
            "single_model_mode": single_model_mode,
        }

    @r.post("/persona/create_from_url")
    def create_persona_from_url(name: str, url: str):
        try:
            safe_name = validate_persona_name(name)
            pdir = persona_dir(cfg or {"persona": {"dir": DEFAULT_PERSONA_DIR}}, safe_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        parsed = urlparse(str(url or "").strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Only http(s) URLs with valid host are allowed")

        try:
            resp = requests.get(parsed.geturl(), timeout=10.0)
            resp.raise_for_status()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch persona URL: {exc}") from exc

        raw_bytes = resp.content or resp.text.encode("utf-8", errors="replace")
        if len(raw_bytes) > _MAX_PERSONA_BYTES:
            raise HTTPException(status_code=413, detail="Persona URL content exceeds size limit")

        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, "persona.txt"), "w", encoding="utf-8") as f:
            f.write(resp.text)
        open(os.path.join(pdir, "urls.txt"), "a", encoding="utf-8").close()
        return {"ok": True, "name": safe_name}

    return r
