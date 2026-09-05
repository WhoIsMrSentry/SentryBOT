from __future__ import annotations
import logging
import os
from typing import Any, Dict, List
from fastapi import APIRouter
import requests

from modules.ai_provider.api._helpers import persona_dir, load_persona_text, should_use_persona_model
from modules.ai_provider.services.chat import OllamaChatService

logger = logging.getLogger("ollama.api")


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

    @r.get("/persona")
    def get_persona():
        return {"ok": True, "active": runtime["active_persona"], "persona": runtime["persona_text"][:4096]}

    @r.get("/personas")
    def list_personas() -> dict:
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        items: List[str] = []
        if os.path.exists(base):
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name)):
                    items.append(name)
        return {"ok": True, "items": items, "active": runtime["active_persona"]}

    @r.post("/persona/select")
    def select_persona(name: str):
        pdir = persona_dir(cfg, name)
        path = os.path.join(pdir, "persona.txt")
        if not os.path.exists(path):
            return {"ok": False, "error": "persona not found"}

        runtime["active_persona"] = str(name)
        raw_content = load_persona_text(cfg, name)

        if "FROM " in raw_content and "SYSTEM " in raw_content:
            modelfile = raw_content
        else:
            base_model = str(cfg.get("ollama", {}).get("model", "qwen3.5:9b"))
            modelfile = f'FROM {base_model}\nSYSTEM """\n{raw_content}\n"""'

        success = False
        if provider_name == "ollama" and not single_model_mode and use_persona_models:
            success = client.create_model(name, modelfile)
            if not success:
                logger.error(f"Failed to create model for persona {name}")
        elif provider_name == "ollama":
            logger.info("Persona model creation disabled (single_model_mode/use_persona_models) for '%s'.", name)

        runtime["persona_text"] = raw_content
        runtime["_persona_cache"][name] = raw_content

        chat = OllamaChatService(
            client,
            persona_name=runtime["active_persona"],
            max_history=6,
            use_persona_as_model=should_use_persona_model(provider_name, single_model_mode, use_persona_models),
            num_predict=ollama_num_predict,
        )
        runtime["chat"] = chat

        return {
            "ok": True,
            "active": name,
            "provider": provider_name,
            "model_created": success if provider_name == "ollama" else None,
            "single_model_mode": single_model_mode,
        }

    @r.post("/persona/create_from_url")
    def create_persona_from_url(name: str, url: str):
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        pdir = os.path.join(base, name)
        os.makedirs(pdir, exist_ok=True)
        resp = requests.get(url)
        resp.raise_for_status()
        with open(os.path.join(pdir, "persona.txt"), "w", encoding="utf-8") as f:
            f.write(resp.text)
        open(os.path.join(pdir, "urls.txt"), "a", encoding="utf-8").close()
        return {"ok": True, "name": name}

    return r
