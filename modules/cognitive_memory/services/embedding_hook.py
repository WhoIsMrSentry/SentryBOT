"""Central hook to attach the shared ONNX System1EmbedEngine to cognitive memory RAGs."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("cognitive_memory.embedding_hook")


def hook_embedding_provider(rag: Any, name: str = "rag") -> None:
    """Attach the embedding vector function from the shared ONNX embedding singleton."""
    try:
        from modules.agent_core.services.system1_embed import System1EmbedEngine

        engine = System1EmbedEngine.get_instance()
        if engine.enabled:
            rag.set_embedding_provider(engine.embed_vector)
            logger.info("%s semantic rerank hooked (shared System1EmbedEngine singleton)", name)
    except Exception:
        pass


__all__ = ["hook_embedding_provider"]

