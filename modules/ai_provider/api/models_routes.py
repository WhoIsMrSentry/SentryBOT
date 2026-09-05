from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import APIRouter

logger = logging.getLogger("ollama.api")


def get_models_router(
    client: Any,
    provider_name: str,
    model: str,
    cfg: dict,
    runtime: dict,
) -> APIRouter:
    r = APIRouter(tags=["ollama-models"])

    @r.get("/models")
    def list_models() -> Dict[str, Any]:
        if provider_name != "ollama":
            return {"ok": False, "provider": provider_name, "items": [], "error": "model listing is only supported for ollama provider"}
        items = client.list_models()
        return {"ok": True, "provider": provider_name, "items": items, "active": model}

    @r.post("/model/add")
    def add_model(name: str, set_default: bool = True) -> Dict[str, Any]:
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
            runtime["model"] = model_name
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

    @r.post("/warmup")
    def warmup() -> Dict[str, Any]:
        try:
            chat = runtime.get("chat")
            if chat:
                _ = chat.chat("ok")
            return {"ok": True}
        except Exception as exc:
            logger.debug("Warmup failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    return r
