from __future__ import annotations

import logging
import threading
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
    rt_lock = runtime.setdefault("_lock", threading.RLock())

    @r.get("/models")
    def list_models() -> Dict[str, Any]:
        if provider_name != "ollama":
            return {
                "ok": False,
                "provider": provider_name,
                "items": [],
                "error": "model listing is only supported for ollama provider",
            }
        items = client.list_models()
        with rt_lock:
            active_model = str(runtime.get("model") or model)
        return {"ok": True, "provider": provider_name, "items": items, "active": active_model}

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
            with rt_lock:
                cfg.setdefault("ollama", {})["model"] = model_name
                runtime["model"] = model_name
                if hasattr(client, "model"):
                    setattr(client, "model", model_name)

        with rt_lock:
            default_model = str(runtime.get("model") or cfg.get("ollama", {}).get("model", model_name))

        return {
            "ok": True,
            "provider": provider_name,
            "model": model_name,
            "set_default": bool(set_default),
            "default_model": default_model,
            "available": client.list_models(),
        }

    @r.post("/warmup")
    def warmup() -> Dict[str, Any]:
        try:
            with rt_lock:
                active_chat = runtime.get("chat")
            if active_chat:
                _ = active_chat.chat("ok")
            return {"ok": True}
        except Exception as exc:
            logger.debug("Warmup failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    return r
