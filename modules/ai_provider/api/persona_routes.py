from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException
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
from modules.ai_provider.services.persona_rag import PersonaManager, load_persona_manifest
from modules.common.persona_scope import get_active_persona, set_active_persona

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
        mf_path = os.path.join(pdir, "modelfile")
        if not os.path.exists(path) and not os.path.exists(mf_path):
            return {"ok": False, "error": "persona not found"}

        manifest = load_persona_manifest(Path(pdir))
        raw_content = load_persona_text(cfg, safe_name)
        from modules.common.model_roles import DEFAULT_UTILITY_MODEL
        from modules.common.ollama_modelfile import load_or_build_persona_modelfile

        base_model = str(manifest.get("base_model") or DEFAULT_UTILITY_MODEL).strip()
        model_tag = str(manifest.get("model") or f"{safe_name}:latest").strip()
        modelfile = load_or_build_persona_modelfile(Path(pdir), base_model=base_model)

        success = False
        if provider_name == "ollama" and not single_model_mode and use_persona_models and client is not None:
            success = client.create_model(model_tag, modelfile)
            if not success:
                logger.warning("Remote Ollama create_model skipped/failed for persona %s (%s)", safe_name, model_tag)
        elif provider_name == "ollama":
            logger.info("Persona model creation disabled (single_model_mode/use_persona_models) for '%s'.", safe_name)

        use_persona_flag = should_use_persona_model(provider_name, single_model_mode, use_persona_models)
        chat_model_target = model_tag if use_persona_flag else safe_name
        with rt_lock:
            runtime["active_persona"] = safe_name
            runtime["persona_text"] = raw_content
            runtime["_persona_cache"][safe_name] = raw_content
            existing_chat = runtime.get("chat")
            if existing_chat is not None and hasattr(existing_chat, "update_persona"):
                existing_chat.update_persona(chat_model_target, use_persona_flag)
            else:
                runtime["chat"] = OllamaChatService(
                    client,
                    persona_name=chat_model_target,
                    max_history=6,
                    use_persona_as_model=use_persona_flag,
                    num_predict=ollama_num_predict,
                )
        set_active_persona(safe_name, meta=manifest)

        return {
            "ok": True,
            "active": safe_name,
            "model": model_tag if use_persona_flag else runtime.get("model"),
            "provider": provider_name,
            "model_created": success if provider_name == "ollama" else None,
            "single_model_mode": single_model_mode,
            "meta": manifest,
        }

    @r.post("/persona/create")
    def create_persona_from_spec(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        raw_name = str(payload.get("name") or "").strip()
        instructions = str(payload.get("instructions") or payload.get("persona_txt") or "").strip()
        try:
            safe_name = validate_persona_name(raw_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not instructions:
            raise HTTPException(status_code=400, detail="instructions cannot be empty")
        mgr = PersonaManager(persona_base_dir(cfg))
        try:
            urls = payload.get("urls") if isinstance(payload.get("urls"), list) else []
            return mgr.create_persona(
                safe_name,
                instructions,
                urls=urls,
                base_model=str(payload.get("base_model") or "nemotron-3.5-bolt:e4b"),
                display_name=str(payload.get("display_name") or ""),
                response_language=str(payload.get("response_language") or "follow_user"),
                tts_voice=payload.get("tts_voice"),
                tts_voice_en=payload.get("tts_voice_en"),
                default_emotion=str(payload.get("default_emotion") or "neutral"),
                aliases=payload.get("aliases") if isinstance(payload.get("aliases"), list) else None,
                create_model=bool(payload.get("create_model", True) and provider_name == "ollama"),
                ollama_client=client,
                fetch_urls=bool(payload.get("fetch_urls", True)),
            )
        finally:
            mgr.close()

    @r.post("/persona/ingest")
    def ingest_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        raw_name = str(payload.get("name") or get_active_persona()).strip()
        try:
            safe_name = validate_persona_name(raw_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        mgr = PersonaManager(persona_base_dir(cfg))
        try:
            rag = mgr.get_rag(safe_name)
            urls = payload.get("urls")
            if isinstance(urls, list) and urls:
                cleaned = [str(u).strip() for u in urls if str(u).strip().startswith(("http://", "https://"))]
                merged = list(dict.fromkeys([*rag.read_urls(), *cleaned]))
                rag.persona_dir.mkdir(parents=True, exist_ok=True)
                rag.urls_path.write_text("\n".join(merged) + ("\n" if merged else ""), encoding="utf-8")
            return rag.ingest(
                fetch_urls=bool(payload.get("fetch_urls", True)),
                force_fetch=bool(payload.get("force_fetch", False)),
                clear_missing=bool(payload.get("clear_missing", False)),
            )
        finally:
            mgr.close()

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
        urls_file = Path(pdir) / "urls.txt"
        existing_urls = urls_file.read_text(encoding="utf-8").splitlines() if urls_file.is_file() else []
        if parsed.geturl() not in existing_urls:
            with open(urls_file, "a", encoding="utf-8") as f:
                f.write(f"{parsed.geturl()}\n")
        return {"ok": True, "name": safe_name}

    return r
