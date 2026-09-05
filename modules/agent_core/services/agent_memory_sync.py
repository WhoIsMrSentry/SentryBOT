from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.orchestrator")


class AgentMemorySyncMixin:
    """Memory consolidation, world context injection, and dialogue observation for AgentOrchestrator."""

    memory: Any
    world_state: Any
    config: Dict[str, Any]
    fast_path_enabled: bool
    fast_path_max_chars: int
    persona_system_prompt: str
    chat_history: List[Dict[str, Any]]
    progress_manager: Any

    def _build_memory_consolidator(self) -> Any:
        try:
            from .memory_consolidator import MemoryConsolidator
            return MemoryConsolidator(
                memory=getattr(self, "memory", None),
                autonomy_client=getattr(self, "autonomy_client", None),
            )
        except Exception as exc:
            logger.warning("MemoryConsolidator not available: %s", exc)
            return None

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

    @staticmethod
    def _normalize_session_language(language: Optional[str]) -> str:
        lang = str(language or "tr").strip().lower()
        return lang if lang in {"tr", "en", "de", "es", "fr"} else "tr"

    @staticmethod
    def _language_directive(lang: str) -> str:
        try:
            from modules.common.lang_names import get_language_name
            lang_name = get_language_name(lang)
        except Exception:
            lang_name = ""
        label = lang_name or f"the language with ISO code '{lang}'"
        return (
            f"The user is speaking {label} (ISO code: {lang}). "
            f"Reply ONLY in that language. Do not mix in other languages."
        )

    def _build_progress_callback(self, progress_token: str, progress_cb: Optional[Callable] = None) -> Callable:
        def _unified_progress_cb(event: Dict[str, Any]) -> None:
            event["token"] = progress_token
            self.progress_manager.on_progress_event(event)
            if progress_cb:
                try:
                    progress_cb(event)
                except Exception:
                    pass
        return _unified_progress_cb

    def _should_fast_path(self, user_prompt: str, *, native_tools: bool = False) -> bool:
        if native_tools:
            return True
        if not self.fast_path_enabled:
            return False
        return len(str(user_prompt or "").strip()) <= self.fast_path_max_chars

    def _native_loop_messages(self, session_language: str) -> List[Dict[str, Any]]:
        try:
            from modules.common.system_prompts import persona_prompt_with_language
        except Exception:
            persona_prompt_with_language = None
        lang_rule = self._language_directive(session_language)
        if persona_prompt_with_language is not None:
            system_prompt = persona_prompt_with_language(self.persona_system_prompt, lang_rule)
        else:
            persona = self.persona_system_prompt or (
                "You are the robot's single response layer. Answer the user directly."
            )
            system_prompt = (
                f"{persona}\n\n{lang_rule}\n\n"
                "You understand the user in any language. Interpret intent across languages "
                "(e.g. LED color, emotion, speak, head movement) and call the matching tool.\n"
                "You can control the robot with the available tools (lights, emotion, "
                "speech, head, sounds...). When the user asks for a physical action, "
                "call the matching tool instead of only describing it, then confirm "
                "briefly in one sentence in the user's language."
            )
        return [{"role": "system", "content": system_prompt}] + list(self.chat_history)
