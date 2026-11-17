from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agent.orchestrator")


class AgentFastPathMixin:
    """Fast-path dispatching, language directives, and prompt assembly for AgentOrchestrator."""

    config: Dict[str, Any]
    fast_path_enabled: bool
    fast_path_max_chars: int
    persona_system_prompt: str
    chat_history: List[Dict[str, Any]]
    progress_manager: Any
    world_state: Any
    _last_laya_fast_path_decision: Any

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
            if hasattr(self, "progress_manager") and self.progress_manager:
                self.progress_manager.on_progress_event(event)
            if progress_cb:
                try:
                    progress_cb(event)
                except Exception:
                    pass
        return _unified_progress_cb

    def _should_fast_path(self, user_prompt: str, *, native_tools: bool = False) -> bool:
        self._last_laya_fast_path_decision = None
        if native_tools:
            return True
        if not getattr(self, "fast_path_enabled", False):
            return False

        # System 1 Laya fast-path check (skip for background/autonomous ack-suppressed turns)
        ack_suppressed = bool(hasattr(self, "_is_ack_suppressed") and self._is_ack_suppressed())
        laya_engine = getattr(self, "laya_engine", None)
        if not ack_suppressed and laya_engine is not None and getattr(laya_engine, "enabled", True):
            try:
                world_state = (
                    self.world_state.get_state()
                    if hasattr(self, "world_state") and hasattr(self.world_state, "get_state")
                    else None
                )
                visual_context = (
                    self.world_state.get_laya_scene_summary()
                    if hasattr(self, "world_state") and hasattr(self.world_state, "get_laya_scene_summary")
                    else None
                )
                try:
                    is_fast, decision = laya_engine.should_fast_path(
                        user_prompt,
                        world_state=world_state,
                        visual_context=visual_context,
                    )
                except TypeError:
                    # Keep compatibility with injected pre-context Laya adapters.
                    is_fast, decision = laya_engine.should_fast_path(user_prompt)
                self._last_laya_fast_path_decision = decision
                if is_fast:
                    return True
                if decision is not None and not decision.is_direct_command:
                    return False
            except Exception:
                pass

        max_chars = getattr(self, "fast_path_max_chars", 180)
        return len(str(user_prompt or "").strip()) <= max_chars

    def _native_loop_messages(
        self,
        session_language: str,
        world_context: str = "",
        survival_override: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            from modules.common.system_prompts import persona_prompt_with_language
        except Exception:
            persona_prompt_with_language = None
        lang_rule = self._language_directive(session_language)
        if persona_prompt_with_language is not None:
            system_prompt = persona_prompt_with_language(self.persona_system_prompt, lang_rule)
        else:
            persona = getattr(self, "persona_system_prompt", "") or (
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
        if survival_override:
            system_prompt = f"{system_prompt}\n\n{survival_override}"
        if world_context:
            system_prompt = f"{system_prompt}\n\n[World State]\n{world_context}"
        get_snap = getattr(self, "_get_history_snapshot", None)
        history = get_snap() if callable(get_snap) else list(getattr(self, "chat_history", []))
        dec = getattr(self, "_last_laya_fast_path_decision", None)
        raw_ans = getattr(dec, "raw_answers", None) if dec is not None else None
        action_hint = raw_ans.get("action_hint") if isinstance(raw_ans, dict) else None
        if isinstance(action_hint, dict) and action_hint:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"[SYSTEM1 SEMANTIC HINT] Implied parameters for this indirect request: {action_hint}"
            )
        from modules.common.model_roles import ROLE_CODER, explicit_single_model_mode, infer_prompt_role

        if explicit_single_model_mode(getattr(self, "config", None)) is False:
            last_user = ""
            for item in reversed(history):
                if isinstance(item, dict) and item.get("role") == "user":
                    last_user = str(item.get("content") or "")
                    break
            if infer_prompt_role(last_user) == ROLE_CODER:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    "[CODING TASK] Focus on clean, accurate code and concise technical explanation. "
                    "Only invoke robot hardware/motion/light tools if explicitly asked."
                )
        return [{"role": "system", "content": system_prompt}] + history
