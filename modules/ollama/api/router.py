from __future__ import annotations
import logging
import os

from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
import requests

try:
    from ..services.clients import create_llm_client
    from ..services.chat import PersonaProvider, OllamaChatService
    from ..services.translator import OllamaTranslator
except Exception:
    from services.clients import create_llm_client  # type: ignore
    from services.chat import PersonaProvider, OllamaChatService  # type: ignore
    from services.translator import OllamaTranslator  # type: ignore


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


logger = logging.getLogger("ollama.api")


def get_router(cfg: dict) -> APIRouter:
    r = APIRouter(prefix="/ollama", tags=["ollama"])

    provider_name = "ollama"
    try:
        client, provider_name = create_llm_client(cfg)
    except Exception as exc:
        logger.warning("LLM provider init failed, fallback to ollama: %s", exc)
        fallback_cfg = {
            "llm": {"provider": "ollama"},
            "ollama": cfg.get("ollama", {}) or {},
        }
        client, provider_name = create_llm_client(fallback_cfg)

    model = str(getattr(client, "model", cfg.get("ollama", {}).get("model", "unknown")))
    translator = OllamaTranslator(client, cfg.get("translation", {}) or {})
    actions_cfg = cfg.get("actions", {}) or {}
    action_endpoint = str(actions_cfg.get("endpoint", "")).strip()
    action_timeout = float(actions_cfg.get("timeout", 1.5))
    default_apply = bool(actions_cfg.get("default_apply", False))

    active_persona = str(cfg.get("persona", {}).get("default", "sentry"))
    persona_text = _load_persona_text(cfg, active_persona)
    chat = OllamaChatService(client, persona_name=active_persona, max_history=6)
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
        info: Dict[str, Any] = {"ok": True, "provider": provider_name, "model": model}
        if provider_name == "ollama":
            info["base_url"] = str(cfg.get("ollama", {}).get("base_url", "http://localhost:11435"))
        elif provider_name == "google_ai_studio":
            info["base_url"] = str(cfg.get("google_ai_studio", {}).get("base_url", "https://generativelanguage.googleapis.com"))
        return info

    def _format_chat_payload(result: Dict[str, Any], translation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True, 
            "answer": result.get("text", ""),
            "text": result.get("text", ""),
            "thoughts": result.get("thoughts", ""),
            "persona": active_persona,
            "model": model,
            "provider": provider_name,
        }
        if result.get("actions"):
            payload["actions"] = result["actions"]
        if "raw" in result:
            payload["raw"] = result.get("raw")
        if translation:
            payload["translation"] = translation
        return payload

    def _maybe_dispatch_actions(result: Dict[str, Any], apply_flag: bool) -> None:
        if not apply_flag or not action_endpoint:
            return
        actions = result.get("actions")
        if not actions:
            return
        payload = {
            "text": result.get("text", ""),
            "raw": result.get("raw"),
            "actions": actions,
            "speak": False,
        }
        try:
            requests.post(action_endpoint, json=payload, timeout=action_timeout)
        except Exception as exc:  # pragma: no cover - ağ hatası
            logger.warning("Failed to dispatch persona actions: %s", exc)

    @r.get("/chat")
    def chat_get(
        query: str = Query(...),
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        if source == "auto":
            source = translator.detect_language(query)
        target = translator.normalize_lang(response_lang or source, fallback=translator.cfg.default_source_lang)
        query_en = translator.to_bridge(query, source)
        result = chat.chat(query_en)
        answer_en = str(result.get("text", ""))
        localized_answer = translator.from_bridge(answer_en, target)
        result["text"] = localized_answer
        flag = default_apply if apply_actions is None else apply_actions
        _maybe_dispatch_actions(result, flag)
        translation_meta = {
            "enabled": bool(translator.cfg.enabled),
            "request_lang": source,
            "bridge_lang": translator.BRIDGE_LANG,
            "response_lang": target,
            "query_bridge": query_en,
            "answer_bridge": answer_en,
            "auto_detected": bool(source_lang and str(source_lang).strip().lower() == "auto"),
        }
        return _format_chat_payload(result, translation=translation_meta)

    @r.post("/chat")
    def chat_post(
        query: str,
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        if source == "auto":
            source = translator.detect_language(query)
        target = translator.normalize_lang(response_lang or source, fallback=translator.cfg.default_source_lang)
        query_en = translator.to_bridge(query, source)
        result = chat.chat(query_en)
        answer_en = str(result.get("text", ""))
        localized_answer = translator.from_bridge(answer_en, target)
        result["text"] = localized_answer
        flag = default_apply if apply_actions is None else apply_actions
        _maybe_dispatch_actions(result, flag)
        translation_meta = {
            "enabled": bool(translator.cfg.enabled),
            "request_lang": source,
            "bridge_lang": translator.BRIDGE_LANG,
            "response_lang": target,
            "query_bridge": query_en,
            "answer_bridge": answer_en,
            "auto_detected": bool(source_lang and str(source_lang).strip().lower() == "auto"),
        }
        return _format_chat_payload(result, translation=translation_meta)

    @r.post("/translate")
    def translate(text: str, source_lang: str = "auto", target_lang: str = "en"):
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        target = translator.normalize_lang(target_lang, fallback=translator.BRIDGE_LANG)
        if source_lang == "auto":
            source = translator.detect_language(text)
        out = translator.translate(text, source, target)
        return {"ok": True, "text": out, "source_lang": source, "target_lang": target}

    @r.get("/persona")
    def get_persona():
        return {"ok": True, "active": active_persona, "persona": persona_text[:4096]}

    @r.get("/personas")
    def list_personas() -> dict:
        base = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
        items: List[str] = []
        if os.path.exists(base):
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name)):
                    items.append(name)
        return {"ok": True, "items": items, "active": active_persona}

    @r.post("/persona/select")
    def select_persona(name: str):
        nonlocal persona_text, chat, active_persona
        pdir = _persona_dir(cfg, name)
        path = os.path.join(pdir, "persona.txt")
        if not os.path.exists(path):
            return {"ok": False, "error": "persona not found"}
        
        active_persona = str(name)
        raw_content = _load_persona_text(cfg, name)
        
        # Hybrid Modelfile Detection
        if "FROM " in raw_content and "SYSTEM " in raw_content:
            modelfile = raw_content
        else:
            # Wrap legacy persona in a default template
            base_model = str(cfg.get("ollama", {}).get("model", "qwen3.5:2b"))
            modelfile = f'FROM {base_model}\nSYSTEM """\n{raw_content}\n"""'

        # Create/Update the model in Ollama
        success = client.create_model(name, modelfile)
        if not success:
            logger.error(f"Failed to create model for persona {name}")
            
        persona_text = raw_content
        _persona_cache[name] = persona_text
        chat = OllamaChatService(client, persona_name=active_persona, max_history=6)
        return {"ok": True, "active": name, "model_created": success}

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
