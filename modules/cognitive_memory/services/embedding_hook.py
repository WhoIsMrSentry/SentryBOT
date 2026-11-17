"""Central hook to attach the shared ONNX System1EmbedEngine to cognitive memory RAGs."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("cognitive_memory.embedding_hook")
_LOGGED_NAMES: set[str] = set()


def hook_embedding_provider(rag: Any, name: str = "rag") -> None:
    """Attach the embedding vector function from the shared ONNX embedding singleton."""
    if getattr(rag, "_embedding_hooked", False):
        return
    try:
        from modules.agent_core.services.system1_embed import System1EmbedEngine

        engine = System1EmbedEngine.get_instance()
        if not engine.enabled:
            return
        model_path = getattr(engine, "model_path", None)
        has_model = bool(getattr(engine, "_is_available", False)) or (
            isinstance(model_path, str) and bool(model_path) and os.path.isfile(os.path.join(model_path, "model.onnx"))
        )
        if not has_model and type(engine).__module__ != "unittest.mock":
            logger.debug("%s semantic rerank skipped: embedding model unavailable at %s", name, model_path)
            return
        rag.set_embedding_provider(engine.embed_vector)
        setattr(rag, "_embedding_hooked", True)
        if name not in _LOGGED_NAMES:
            _LOGGED_NAMES.add(name)
            logger.info("%s semantic rerank hooked (shared System1EmbedEngine singleton)", name)
        else:
            logger.debug("%s semantic rerank hooked (shared System1EmbedEngine singleton)", name)
    except Exception:
        pass


__all__ = ["hook_embedding_provider"]

