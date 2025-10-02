from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Optional, List, Dict
import os
import requests

try:
    from ..services.clients import OllamaClient
    from ..services.chat import PersonaProvider, OllamaChatService
except Exception:
    from services.clients import OllamaClient  # type: ignore
    from services.chat import PersonaProvider, OllamaChatService  # type: ignore


def _persona_dir(cfg: dict, name: Optional[str] = None) -> str:
    pdir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    pname = name or str(cfg.get("persona", {}).get("default", "glados"))
    return os.path.join(pdir, pname)


def _load_persona_text(cfg: dict, name: Optional[str] = None) -> str:
    pdir = _persona_dir(cfg, name)
    path = os.path.join(pdir, "persona.txt")
    if not os.path.exists(path):
        return "You are a helpful assistant."
    with open(path, "r", encoding="utf-8") as f:
        return "".join([line for line in f if len(line.strip()) > 0 and not line.strip().startswith("#")])


def get_router(cfg: dict) -> APIRouter:
    r = APIRouter(prefix="/ollama", tags=["ollama"])

    base_url = str(cfg.get("ollama", {}).get("base_url", "http://localhost:11434"))
    model = str(cfg.get("ollama", {}).get("model", "llama3.2:3b"))
    timeout = float(cfg.get("ollama", {}).get("request_timeout", 60.0))
    client = OllamaClient(base_url=base_url, model=model, request_timeout=timeout)

    persona_text = _load_persona_text(cfg)
    chat = OllamaChatService(client, PersonaProvider(persona_text), max_history=6)
    # Preload persona texts and optional urls placeholders
    _persona_cache: Dict[str, str] = {}
    base_persona_dir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    if os.path.exists(base_persona_dir):
        for name in os.listdir(base_persona_dir):
            pdir = os.path.join(base_persona_dir, name)
            if not os.path.isdir(pdir):
                continue
            _persona_cache[name] = _load_persona_text(cfg, name)
            urls_path = os.path.join(pdir, "urls.txt")
            if not os.path.exists(urls_path):
                try:
                    open(urls_path, "a", encoding="utf-8").close()
                except Exception:
                    pass

    @r.get("/healthz")
    def healthz():
        return {"ok": True, "base_url": base_url, "model": model}

    @r.get("/chat")
    def chat_get(query: str = Query(...)):
        answer = chat.chat(query)
        return {"ok": True, "answer": answer}

    @r.post("/chat")
    def chat_post(query: str):
        answer = chat.chat(query)
        return {"ok": True, "answer": answer}

    @r.get("/persona")
    def get_persona():
        return {"ok": True, "persona": persona_text[:4096]}

    @r.get("/personas")
    def list_personas() -> dict:
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        items: List[str] = []
        if os.path.exists(base):
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name)):
                    items.append(name)
        return {"ok": True, "items": items, "active": cfg.get("persona", {}).get("default")}

    @r.post("/persona/select")
    def select_persona(name: str):
        nonlocal persona_text, chat
        pdir = _persona_dir(cfg, name)
        path = os.path.join(pdir, "persona.txt")
        if not os.path.exists(path):
            return {"ok": False, "error": "persona not found"}
        persona_text = _persona_cache.get(name) or _load_persona_text(cfg, name)
        _persona_cache[name] = persona_text
        chat = OllamaChatService(client, PersonaProvider(persona_text), max_history=6)
        return {"ok": True, "active": name}

    @r.post("/persona/create_from_url")
    def create_persona_from_url(name: str, url: str):
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        pdir = os.path.join(base, name)
        os.makedirs(pdir, exist_ok=True)
        resp = requests.get(url)
        resp.raise_for_status()
        with open(os.path.join(pdir, "persona.txt"), "w", encoding="utf-8") as f:
            f.write(resp.text)
        # create empty urls placeholder
        open(os.path.join(pdir, "urls.txt"), "a", encoding="utf-8").close()
        return {"ok": True, "name": name}

    return r
