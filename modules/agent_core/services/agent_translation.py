"""Bridge translation helpers for AgentOrchestrator (source <-> EN <-> target)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agent.translation")

_COMPANION_SUFFIX_RE = re.compile(r"(\n*\[CompanionContext\b.*)$", re.DOTALL)


def extract_translation_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve translation config dict from root or sub-sections (disabled unless enabled)."""
    cfg = config if isinstance(config, dict) else {}
    for section in (
        cfg.get("translation"),
        (cfg.get("agent") or {}).get("translation") if isinstance(cfg.get("agent"), dict) else None,
        (cfg.get("ollama_service") or {}).get("translation") if isinstance(cfg.get("ollama_service"), dict) else None,
    ):
        if isinstance(section, dict) and section:
            out = dict(section)
            out.setdefault("enabled", False)
            return out
    return {"enabled": False}


def split_companion_suffix(text: str) -> Tuple[str, str]:
    """Separate trailing ``[CompanionContext ...]`` metadata from spoken prompt text."""
    raw = str(text or "")
    match = _COMPANION_SUFFIX_RE.search(raw)
    if not match:
        return raw, ""
    head = raw[: match.start()].rstrip()
    tail = match.group(1)
    return head, tail


class AgentTranslationMixin:
    """Keeps System 1 on raw user text while bridging System 2 LLM turns via English."""

    translator: Any
    config: Dict[str, Any]

    def _init_translator(self, config: Dict[str, Any]) -> None:
        tcfg = extract_translation_config(config)
        self.translator = None
        if not bool(tcfg.get("enabled", False)):
            return
        try:
            from modules.common.translator import get_shared_translator

            self.translator = get_shared_translator(
                tcfg,
                ollama_client=getattr(self, "ollama_client", None),
            )
        except Exception as exc:
            logger.warning("Agent translation init failed: %s", exc)
            self.translator = None

    def _effective_response_language(self, session_language: str) -> str:
        override = str(getattr(self, "_persona_response_language", "") or "").strip().lower()
        if override and override not in {"auto", "follow_user", "user"}:
            return override
        return str(session_language or "tr").strip().lower() or "tr"

    def _bridge_translation_active(
        self,
        session_language: str,
        *,
        event_type: Optional[str] = None,
    ) -> bool:
        tr = getattr(self, "translator", None)
        if tr is None or not getattr(getattr(tr, "cfg", None), "enabled", False):
            return False
        bridge = str(getattr(tr, "BRIDGE_LANG", "en") or "en").lower()
        src = str(session_language or "tr").strip().lower()
        tgt = self._effective_response_language(session_language)
        if event_type and tgt == bridge:
            return False
        return src != bridge or tgt != bridge

    def _translate_prompt_for_llm(
        self,
        prompt: str,
        session_language: str,
        *,
        event_type: Optional[str] = None,
    ) -> str:
        if not prompt or not self._bridge_translation_active(session_language, event_type=event_type):
            return prompt
        head, tail = split_companion_suffix(prompt)
        if not head.strip():
            return prompt
        src = "auto" if event_type else session_language
        translated = self.translator.to_bridge(head, src)
        return f"{translated}{tail}" if tail else translated

    def _translate_history_for_llm(
        self,
        history: List[Dict[str, Any]],
        session_language: str,
        *,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not history or not self._bridge_translation_active(session_language, event_type=event_type):
            return history
        out: List[Dict[str, Any]] = []
        last_idx = len(history) - 1
        for idx, item in enumerate(history):
            if not isinstance(item, dict):
                out.append(item)
                continue
            role = str(item.get("role", "")).lower()
            content = str(item.get("content") or "")
            if role in {"user", "assistant"} and content.strip():
                copy_item = dict(item)
                if role == "user":
                    src_hint = "auto" if (idx < last_idx or event_type) else session_language
                    copy_item["content"] = self._translate_prompt_for_llm(
                        content, src_hint, event_type=event_type if idx == last_idx else None
                    )
                else:
                    copy_item["content"] = self.translator.to_bridge(content, "auto")
                out.append(copy_item)
            else:
                out.append(item)
        return out

    def _translate_output_from_llm(
        self,
        text: str,
        session_language: str,
        *,
        event_type: Optional[str] = None,
    ) -> str:
        raw = str(text or "")
        if not raw.strip() or not self._bridge_translation_active(session_language, event_type=event_type):
            return raw
        target = self._effective_response_language(session_language)
        bridge = str(getattr(self.translator, "BRIDGE_LANG", "en") or "en").lower()
        if target == bridge:
            return raw
        return self.translator.from_bridge(raw, target)

    def _localize_tool_speech(
        self,
        text: str,
        explicit_language: str = "",
    ) -> Tuple[str, str]:
        """Translate LLM-emitted English tool speech into active user language."""
        raw = str(text or "").strip()
        target = str(
            getattr(self, "_active_response_language", "") or "tr"
        ).strip().lower() or "tr"
        if not raw:
            return "", target
        tr = getattr(self, "translator", None)
        if tr is None or not getattr(getattr(tr, "cfg", None), "enabled", False):
            return raw, str(explicit_language or target)
        bridge = tr.normalize_lang(getattr(tr, "BRIDGE_LANG", "en"), fallback="en")
        target = tr.normalize_lang(target, fallback=target)
        raw_req = str(explicit_language or "").strip()
        req_lang = tr.normalize_lang(raw_req, fallback="") if raw_req else ""
        if target == bridge:
            return raw, bridge
        # Model explicitly tagged bridge output (e.g. language='en'): translate directly.
        if req_lang == bridge:
            return tr.from_bridge(raw, target), target
        detect_default = (
            bridge
            if getattr(self, "_active_bridge_translation", False)
            else target
        )
        detected = tr.detect_language(raw, default=detect_default)
        # Respect explicit non-bridge target unless the payload itself is non-target (e.g. English).
        if req_lang and req_lang == target and detected == target:
            return raw, req_lang
        if detected == target:
            return raw, target
        localized = tr.from_bridge(raw, target)
        return localized, target
