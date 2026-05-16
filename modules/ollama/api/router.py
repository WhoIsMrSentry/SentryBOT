from __future__ import annotations
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import requests

try:
    from ..services.clients import create_llm_client
    from ..services.chat import OllamaChatService
    from ..services.translator import OllamaTranslator
except Exception:
    # Fallback: prefer explicit absolute module path to avoid ambiguous bare imports
    from modules.ollama.services.clients import create_llm_client  # type: ignore
    from modules.ollama.services.chat import OllamaChatService  # type: ignore
    from modules.ollama.services.translator import OllamaTranslator  # type: ignore


def _persona_dir(cfg: dict, name: Optional[str] = None) -> str:
    pdir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    pname = name or str(cfg.get("persona", {}).get("default", "sentry"))
    return os.path.join(pdir, pname)


def _load_persona_text(cfg: dict, name: Optional[str] = None) -> str:
    pdir = _persona_dir(cfg, name)
    path = os.path.join(pdir, "persona.txt")
    if not os.path.exists(path):
        return "You are a helpful assistant."
    with open(path, "r", encoding="utf-8") as f:
        return "".join([line for line in f if len(line.strip()) > 0 and not line.strip().startswith("#")])


logger = logging.getLogger("ollama.api")


def _should_use_persona_model(
    provider_name: str,
    single_model_mode: bool,
    use_persona_models: bool,
) -> bool:
    return (
        str(provider_name or "").strip().lower() == "ollama"
        and not bool(single_model_mode)
        and bool(use_persona_models)
    )


def get_router(cfg: dict) -> APIRouter:
    r = APIRouter(prefix="/ollama", tags=["ollama"])
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
    single_model_mode = bool(llm_cfg.get("single_model_mode", True))
    use_persona_models = bool(llm_cfg.get("use_persona_models", False))

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
    _ollama_num_predict = int(cfg.get("ollama", {}).get("num_predict", 100))
    chat = OllamaChatService(
        client,
        persona_name=active_persona,
        max_history=6,
        use_persona_as_model=_should_use_persona_model(provider_name, single_model_mode, use_persona_models),
        num_predict=_ollama_num_predict,
    )
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
            info["base_url"] = str(cfg.get("ollama", {}).get("base_url", "http://127.0.0.1:11434"))
        elif provider_name == "google_ai_studio":
            gcfg = cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio", {}), dict) else {}
            info["base_url"] = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com"))
            info["api_key_configured"] = bool(str(gcfg.get("api_key", "")).strip() or os.getenv("GOOGLE_API_KEY"))
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

    def _chat_response(
        query: str,
        apply_actions: Optional[bool],
        source_lang: Optional[str],
        response_lang: Optional[str],
    ) -> Dict[str, Any]:
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        if source == "auto":
            source = translator.detect_language(query)
        target = translator.normalize_lang(response_lang or source, fallback=translator.cfg.default_source_lang)
        query_en = translator.to_bridge(query, source)

        try:
            result = chat.chat(query_en)
        except requests.HTTPError as exc:
            logger.warning("LLM upstream request failed: %s", exc)
            raise HTTPException(status_code=502, detail="LLM upstream request failed") from exc
        except Exception as exc:
            logger.exception("LLM chat failed: %s", exc)
            raise HTTPException(status_code=500, detail="LLM chat failed") from exc

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

    @r.get("/chat")
    def chat_get(
        query: str = Query(...),
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        return _chat_response(query, apply_actions, source_lang, response_lang)

    @r.post("/chat")
    def chat_post(
        query: str,
        apply_actions: Optional[bool] = None,
        structured: bool = False,
        source_lang: Optional[str] = None,
        response_lang: Optional[str] = None,
    ):
        return _chat_response(query, apply_actions, source_lang, response_lang)

    @r.post("/translate")
    def translate(text: str, source_lang: str = "auto", target_lang: str = "en"):
        source = translator.normalize_lang(source_lang, fallback=translator.cfg.default_source_lang)
        target = translator.normalize_lang(target_lang, fallback=translator.BRIDGE_LANG)
        if source_lang == "auto":
            source = translator.detect_language(text)
        out = translator.translate(text, source, target)
        return {"ok": True, "text": out, "source_lang": source, "target_lang": target}

    @r.post("/runtime/num_predict")
    def runtime_num_predict(body: Dict[str, Any]):
        """Hot-adjust default generation horizon for routed chat completions."""
        np_raw = body.get("num_predict")
        if np_raw is None:
            raise HTTPException(status_code=400, detail="num_predict required")
        try:
            np_val = max(48, int(np_raw))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid num_predict: {exc}") from exc
        chat.num_predict = np_val
        return {"ok": True, "num_predict": chat.num_predict}

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

    @r.get("/models")
    def list_models() -> Dict[str, Any]:
        if provider_name != "ollama":
            return {"ok": False, "provider": provider_name, "items": [], "error": "model listing is only supported for ollama provider"}
        items = client.list_models()
        return {"ok": True, "provider": provider_name, "items": items, "active": model}

    @r.post("/warmup")
    def warmup() -> Dict[str, Any]:
        """Best-effort short call to warm model weights/KV cache."""
        try:
            _ = chat.chat("ok")
            return {"ok": True}
        except Exception as exc:
            logger.debug("Warmup failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    @r.post("/model/add")
    def add_model(name: str, set_default: bool = True) -> Dict[str, Any]:
        nonlocal model
        if provider_name != "ollama":
            return {"ok": False, "provider": provider_name, "error": "model add is only supported for ollama provider"}

        model_name = str(name or "").strip()
        if not model_name:
            return {"ok": False, "error": "model name is required"}

        pulled = client.pull_model(model_name)
        if not pulled:
            return {"ok": False, "error": f"failed to pull model '{model_name}'"}

        if set_default:
            cfg.setdefault("ollama", {})["model"] = model_name
            model = model_name
            if hasattr(client, "model"):
                setattr(client, "model", model_name)

        return {
            "ok": True,
            "provider": provider_name,
            "model": model_name,
            "set_default": bool(set_default),
            "default_model": str(cfg.get("ollama", {}).get("model", model_name)),
            "available": client.list_models(),
        }

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
            base_model = str(cfg.get("ollama", {}).get("model", "qwen3.5:9b"))
            modelfile = f'FROM {base_model}\nSYSTEM """\n{raw_content}\n"""'

        success = False
        if provider_name == "ollama" and not single_model_mode and use_persona_models:
            # Create/Update persona model only for Ollama provider.
            success = client.create_model(name, modelfile)
            if not success:
                logger.error(f"Failed to create model for persona {name}")
        elif provider_name == "ollama":
            logger.info("Persona model creation disabled (single_model_mode/use_persona_models) for '%s'.", name)
            
        persona_text = raw_content
        _persona_cache[name] = persona_text
        chat = OllamaChatService(
            client,
            persona_name=active_persona,
            max_history=6,
            use_persona_as_model=_should_use_persona_model(provider_name, single_model_mode, use_persona_models),
            num_predict=_ollama_num_predict,
        )
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
        # create empty urls placeholder
        open(os.path.join(pdir, "urls.txt"), "a", encoding="utf-8").close()
        return {"ok": True, "name": name}

    return r

