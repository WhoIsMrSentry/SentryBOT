from __future__ import annotations

import logging
from typing import Any, Dict

from .agent_fast_path import AgentFastPathMixin

logger = logging.getLogger("agent.orchestrator")


class AgentMemorySyncMixin(AgentFastPathMixin):
    """Memory consolidation, world context injection, and dialogue observation for AgentOrchestrator."""

    memory: Any
    memory_consolidator: Any
    world_state: Any
    config: Dict[str, Any]

    def _build_memory_consolidator(self) -> Any:
        try:
            from .memory_consolidator import MemoryConsolidator

            world_memory = None
            social_db = None
            try:
                from modules.cognitive_memory.services.world_memory import get_default as _wm_default

                world_memory = _wm_default()
            except Exception:
                world_memory = None
            try:
                from modules.cognitive_memory import get_default as _social_default

                social_db = _social_default()
            except Exception:
                social_db = None

            consolidator = MemoryConsolidator(
                memory=getattr(self, "memory", None),
                social_db=social_db,
                autonomy_client=getattr(self, "autonomy_client", None),
                world_memory=world_memory,
                llm_client=getattr(self, "ollama_client", None) or getattr(self, "provider_client", None),
            )
            if getattr(self, "model", None):
                consolidator.llm_model = self.model
            return consolidator
        except Exception as exc:
            logger.warning("MemoryConsolidator not available: %s", exc)
            return None

    def _shutdown_memory_consolidator(self) -> None:
        consolidator = getattr(self, "memory_consolidator", None)
        if consolidator is not None and hasattr(consolidator, "shutdown"):
            try:
                consolidator.shutdown()
            except Exception as exc:
                logger.debug("MemoryConsolidator shutdown failed: %s", exc)

    def _get_world_memory_context(self, query: str = "") -> str:
        consolidator = getattr(self, "memory_consolidator", None)
        if not consolidator or not hasattr(consolidator, "get_context_summary"):
            return ""
        try:
            return consolidator.get_context_summary(query=query) or ""
        except Exception as exc:
            logger.debug("get_world_memory_context failed: %s", exc)
            return ""

    def _observe_world_memory_dialogue(self, user_text: str, bot_text: str) -> None:
        consolidator = getattr(self, "memory_consolidator", None)
        if not consolidator or not hasattr(consolidator, "observe_dialogue"):
            return
        speaker = self._current_speaker()
        try:
            consolidator.observe_dialogue(user_text=user_text, bot_text=bot_text, speaker=speaker)
        except Exception as exc:
            logger.debug("observe_world_memory_dialogue failed: %s", exc)

    def _current_speaker(self) -> str:
        world_state = getattr(self, "world_state", None)
        if world_state and hasattr(world_state, "get_state"):
            try:
                state = world_state.get_state()
                return str(state.get("speaker", "") or "").strip()
            except Exception:
                pass
        return ""
