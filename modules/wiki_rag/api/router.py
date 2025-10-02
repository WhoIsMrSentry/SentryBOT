from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Optional, List
import os
import threading


def _persona_dir(cfg: dict, name: Optional[str] = None) -> str:
    base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    pname = name or str(cfg.get("persona", {}).get("active", "glados"))
    return os.path.join(base, pname)


def _load_persona_text(cfg: dict, name: Optional[str] = None) -> str:
    pdir = _persona_dir(cfg, name)
    path = os.path.join(pdir, "persona.txt")
    if not os.path.exists(path):
        return "You are a helpful assistant."
    with open(path, "r", encoding="utf-8") as f:
        return "".join([line for line in f if len(line.strip()) > 0 and not line.strip().startswith("#")])


def get_router(cfg: dict) -> APIRouter:
    # Prefix is empty here because this module is mounted or included with a prefix by the gateway.
    r = APIRouter(prefix="", tags=["wiki_rag"])

    persist_dir = str(cfg.get("storage", {}).get("persist_dir"))
    knowledge_dir = str(cfg.get("storage", {}).get("knowledge_dir"))
    model = str(cfg.get("ollama", {}).get("model", "llama3.2:3b"))
    timeout = float(cfg.get("ollama", {}).get("request_timeout", 60.0))
    active_persona = str(cfg.get("persona", {}).get("active", "glados"))

    # Lazy import heavy deps; degrade gracefully if missing
    IndexService = None  # type: ignore
    ChatEngineFactory = None  # type: ignore
    try:
        from ..services.indexer import IndexService as _IndexService  # type: ignore
        from ..services.chat import ChatEngineFactory as _ChatEngineFactory  # type: ignore
        IndexService = _IndexService
        ChatEngineFactory = _ChatEngineFactory
    except Exception:
        try:
            from services.indexer import IndexService as _IndexService  # type: ignore
            from services.chat import ChatEngineFactory as _ChatEngineFactory  # type: ignore
            IndexService = _IndexService
            ChatEngineFactory = _ChatEngineFactory
        except Exception:
            IndexService = None  # type: ignore
            ChatEngineFactory = None  # type: ignore

    idx = None
    if IndexService is not None:
        try:
            idx = IndexService(persist_dir, knowledge_dir, model=model, request_timeout=timeout, persona=active_persona)  # type: ignore
        except Exception:
            idx = None

    _index_obj = None
    _chat_engine = None

    def _ensure_index():
        nonlocal _index_obj
        if _index_obj is None and idx is not None:
            _index_obj = idx.build_or_load()
        return _index_obj

    def _ensure_chat():
        nonlocal _chat_engine
        if _chat_engine is None and idx is not None and ChatEngineFactory is not None:
            llm = idx._llm()
            persona_text = _load_persona_text(cfg)
            _chat_engine = ChatEngineFactory(_ensure_index(), llm, persona_text).build()  # type: ignore
        return _chat_engine

    @r.get("/healthz")
    def healthz():
        base_persona_dir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        items: List[dict] = []
        names: List[str] = []
        if os.path.exists(base_persona_dir):
            for name in os.listdir(base_persona_dir):
                if os.path.isdir(os.path.join(base_persona_dir, name)):
                    names.append(name)
        if not names:
            names = [active_persona]
        for name in names:
            pdir = os.path.join(persist_dir, name)
            kdir = os.path.join(knowledge_dir, name)
            ok = os.path.exists(pdir)
            ndocs = len(os.listdir(kdir)) if os.path.exists(kdir) else 0
            items.append({"name": name, "index_built": ok, "num_docs": ndocs})
        return {"ok": True, "active": active_persona, "personas": items}

    @r.get("/personas")
    def list_personas() -> dict:
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        items: List[str] = []
        if os.path.exists(base):
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name)):
                    items.append(name)
        return {"ok": True, "items": items, "active": cfg.get("persona", {}).get("active")}

    @r.post("/persona/select")
    def select_persona(name: str):
        nonlocal _chat_engine
        # reset chat engine to re-read persona
        _chat_engine = None
        # update active in memory (not persisting to file here)
        cfg.setdefault("persona", {})["active"] = name
        return {"ok": True, "active": name}

    @r.post("/preprocess")
    def preprocess():
        try:
            try:
                from ..services.preprocess import fetch_and_convert as _fetch  # type: ignore
            except Exception:
                from services.preprocess import fetch_and_convert as _fetch  # type: ignore
        except Exception as e:
            return {"ok": False, "error": f"preprocess deps missing: {e}"}

        cut_offs = list(cfg.get("preprocess", {}).get("cut_offs", []))
        # persona folder urls.txt
        pdir = _persona_dir(cfg, active_persona)
        os.makedirs(pdir, exist_ok=True)
        urls_path = os.path.join(pdir, "urls.txt")
        kdir = os.path.join(knowledge_dir, active_persona)
        if not os.path.exists(urls_path):
            # create placeholder and return
            open(urls_path, "a", encoding="utf-8").close()
            return {"ok": True, "persona": active_persona, "written": 0, "note": "created urls.txt; please fill and rerun"}
        with open(urls_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        try:
            n = _fetch(urls, kdir, cut_offs=cut_offs)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "persona": active_persona, "written": n}

    @r.post("/index/rebuild")
    def rebuild_index():
        nonlocal _index_obj, _chat_engine
        if idx is None:
            return {"ok": False, "error": "indexer deps missing"}
        _index_obj = None
        _chat_engine = None
        _ensure_index()
        return {"ok": True, "persona": active_persona}

    @r.get("/chat")
    def chat_get(query: str = Query(...)):
        engine = _ensure_chat()
        if engine is None:
            return {"ok": False, "error": "chat deps missing"}
        answer = str(engine.chat(query))
        return {"ok": True, "answer": answer}

    @r.post("/chat")
    def chat_post(query: str):
        engine = _ensure_chat()
        if engine is None:
            return {"ok": False, "error": "chat deps missing"}
        answer = str(engine.chat(query))
        return {"ok": True, "answer": answer}

    # Startup one-time check: if persona-specific URLs exist and persona knowledge missing, run preprocess automatically
    def _bootstrap_all_personas() -> None:
        base_persona_dir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        try:
            try:
                from ..services.preprocess import fetch_and_convert as _fetch_all  # type: ignore
            except Exception:
                from services.preprocess import fetch_and_convert as _fetch_all  # type: ignore
        except Exception:
            _fetch_all = None  # type: ignore

        names: List[str] = []
        if os.path.exists(base_persona_dir):
            for name in os.listdir(base_persona_dir):
                if os.path.isdir(os.path.join(base_persona_dir, name)):
                    names.append(name)

        for name in names:
            try:
                # Ensure urls.txt exists
                pdir = _persona_dir(cfg, name)
                os.makedirs(pdir, exist_ok=True)
                urls_path = os.path.join(pdir, "urls.txt")
                if not os.path.exists(urls_path):
                    open(urls_path, "a", encoding="utf-8").close()

                # Preprocess if knowledge for persona missing/empty
                kdir = os.path.join(knowledge_dir, name)
                if _fetch_all is not None and not (os.path.exists(kdir) and os.listdir(kdir)):
                    with open(urls_path, 'r', encoding='utf-8') as f:
                        urls = [line.strip() for line in f if line.strip()]
                    if urls:
                        try:
                            cut_offs = list(cfg.get("preprocess", {}).get("cut_offs", []))
                            _fetch_all(urls, kdir, cut_offs=cut_offs)
                        except Exception:
                            pass

                # Build/load index for persona to initialize storage
                if IndexService is not None:
                    try:
                        # Pass base dirs; IndexService will scope by persona internally
                        _idx = IndexService(persist_dir, knowledge_dir, model=model, request_timeout=timeout, persona=name)  # type: ignore
                        _ = _idx.build_or_load()
                    except Exception:
                        pass
            except Exception:
                # continue with next persona
                pass

    try:
        threading.Thread(target=_bootstrap_all_personas, daemon=True).start()
    except Exception:
        pass

    return r
