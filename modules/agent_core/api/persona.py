"""Agent Core persona management, remote Modelfile creation, and RAG ingestion HTTP endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from modules.common.persona_scope import get_active_persona


def get_persona_router(agent) -> APIRouter:
    router = APIRouter(tags=["agent-persona"])

    @router.get("/persona")
    def get_persona() -> Dict[str, Any]:
        if hasattr(agent, "get_persona_state"):
            state = agent.get_persona_state()
            if hasattr(agent, "_get_active_persona_model"):
                try:
                    state["model"] = agent._get_active_persona_model()
                except Exception:
                    pass
            return state
        return {"ok": True, "persona": get_active_persona()}

    @router.get("/personas")
    def list_personas() -> Dict[str, Any]:
        mgr = getattr(agent, "persona_manager", None)
        items = mgr.list_personas() if mgr is not None else []
        return {"ok": True, "active": get_active_persona(), "personas": items}

    @router.post("/persona/select")
    def select_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        name = str(payload.get("name") or payload.get("persona") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="missing persona name")
        lang = str(payload.get("response_language") or payload.get("language") or "").strip()
        create_model = bool(payload.get("create_model", False))
        if not hasattr(agent, "apply_persona"):
            raise HTTPException(status_code=501, detail="persona switching not enabled")
        try:
            return agent.apply_persona(
                name,
                response_language=lang,
                ensure_remote_model=create_model,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/persona/create")
    def create_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        instructions = str(payload.get("instructions") or payload.get("persona_txt") or payload.get("system") or "").strip()
        if not name or not instructions:
            raise HTTPException(status_code=400, detail="name and instructions are required")
        if not hasattr(agent, "create_persona"):
            raise HTTPException(status_code=501, detail="persona creation not enabled")
        urls = payload.get("urls") if isinstance(payload.get("urls"), list) else []
        aliases = payload.get("aliases") if isinstance(payload.get("aliases"), list) else None
        try:
            return agent.create_persona(
                name=name,
                instructions=instructions,
                urls=urls,
                base_model=str(payload.get("base_model") or "nemotron-3.5-bolt:e4b"),
                display_name=str(payload.get("display_name") or ""),
                response_language=str(payload.get("response_language") or "follow_user"),
                tts_voice=payload.get("tts_voice"),
                tts_voice_en=payload.get("tts_voice_en"),
                default_emotion=str(payload.get("default_emotion") or "neutral"),
                aliases=aliases,
                create_model=bool(payload.get("create_model", True)),
                fetch_urls=bool(payload.get("fetch_urls", True)),
                activate=bool(payload.get("activate", True)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/persona/ingest")
    def ingest_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        mgr = getattr(agent, "persona_manager", None)
        if mgr is None:
            raise HTTPException(status_code=503, detail="PersonaManager unavailable")
        name = str(payload.get("name") or get_active_persona()).strip()
        try:
            rag = mgr.get_rag(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        extra_urls = payload.get("urls")
        if isinstance(extra_urls, list) and extra_urls:
            merged = list(dict.fromkeys([*rag.read_urls(), *(str(u).strip() for u in extra_urls if str(u).strip().startswith(("http://", "https://")))]))
            rag.persona_dir.mkdir(parents=True, exist_ok=True)
            rag.urls_path.write_text("\n".join(merged) + ("\n" if merged else ""), encoding="utf-8")

        res = rag.ingest(
            fetch_urls=bool(payload.get("fetch_urls", True)),
            force_fetch=bool(payload.get("force_fetch", False)),
            clear_missing=bool(payload.get("clear_missing", False)),
        )
        if bool(payload.get("create_model", False)):
            base_url = str(getattr(agent, "ollama_base_url", "") or "").strip()
            res["ollama_create"] = mgr.ensure_ollama_model(name, base_url=base_url)
        return res

    return router
