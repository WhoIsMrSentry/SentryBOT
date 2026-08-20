from __future__ import annotations
import logging
import os

from fastapi import APIRouter
from typing import Dict

try:
    from ..services.clients import create_llm_client
    from ..services.chat import OllamaChatService
    from ..services.translator import OllamaTranslator
except Exception:
    from modules.ai_provider.services.clients import create_llm_client
    from modules.ai_provider.services.chat import OllamaChatService
    from modules.ai_provider.services.translator import OllamaTranslator

from modules.ai_provider.api._helpers import load_persona_text, should_use_persona_model as _should_use_persona_model
from modules.ai_provider.api.health import get_health_router
from modules.ai_provider.api.chat_routes import get_chat_router
from modules.ai_provider.api.persona_routes import get_persona_router
from modules.ai_provider.api.models_routes import get_models_router

logger = logging.getLogger("ollama.api")


def get_router(cfg: dict) -> APIRouter:
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
    single_model_mode = bool(llm_cfg.get("single_model_mode", True))
    use_persona_models = bool(llm_cfg.get("use_persona_models", False))

    llm_provider_requested = str(llm_cfg.get("provider", "ollama")).strip().lower()
    provider_name = "ollama"
    try:
        client, provider_name = create_llm_client(cfg)
    except Exception as exc:
        if llm_provider_requested in {"google", "google_ai_studio", "gemini"}:
            logger.error(
                "Google AI Studio init failed — set config/agent.yaml google_ai_studio.api_key "
                "or export GOOGLE_API_KEY (profile must not use empty api_key). Error: %s",
                exc,
            )
        logger.warning("LLM provider init failed, fallback to ollama: %s", exc)
        fallback_cfg = {"llm": {"provider": "ollama"}, "ollama": cfg.get("ollama", {}) or {}}
        client, provider_name = create_llm_client(fallback_cfg)

    model = str(getattr(client, "model", cfg.get("ollama", {}).get("model", "unknown")))
    translator = OllamaTranslator(client, cfg.get("translation", {}) or {})
    actions_cfg = cfg.get("actions", {}) or {}
    action_endpoint = str(actions_cfg.get("endpoint", "")).strip()
    action_timeout = float(actions_cfg.get("timeout", 1.5))
    default_apply = bool(actions_cfg.get("default_apply", False))

    active_persona = str(cfg.get("persona", {}).get("default", "sentry"))
    persona_text = load_persona_text(cfg, active_persona)
    ollama_num_predict = int(cfg.get("ollama", {}).get("num_predict", 100))

    chat = OllamaChatService(
        client,
        persona_name=active_persona,
        max_history=6,
        use_persona_as_model=_should_use_persona_model(provider_name, single_model_mode, use_persona_models),
        num_predict=ollama_num_predict,
    )

    _persona_cache: Dict[str, str] = {}
    base_persona_dir = str(cfg.get("persona", {}).get("dir", "modules/ollama/config/personalities"))
    if os.path.exists(base_persona_dir):
        for name in os.listdir(base_persona_dir):
            pdir = os.path.join(base_persona_dir, name)
            if not os.path.isdir(pdir):
                continue
            _persona_cache[name] = load_persona_text(cfg, name)
            urls_path = os.path.join(pdir, "urls.txt")
            if not os.path.exists(urls_path):
                try:
                    open(urls_path, "a", encoding="utf-8").close()
                except Exception:
                    pass

    runtime = {
        "model": model,
        "active_persona": active_persona,
        "persona_text": persona_text,
        "chat": chat,
        "_persona_cache": _persona_cache,
    }

    r = APIRouter(prefix="/ollama", tags=["ollama"])

    r.include_router(get_health_router(cfg, provider_name, model))
    r.include_router(get_chat_router(
        chat, translator, model, provider_name, active_persona,
        action_endpoint, action_timeout, default_apply,
    ))
    r.include_router(get_persona_router(
        cfg, client, provider_name, single_model_mode, use_persona_models, ollama_num_predict, runtime,
    ))
    r.include_router(get_models_router(client, provider_name, model, cfg, runtime))

    return r
