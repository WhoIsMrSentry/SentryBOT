"""Persona switching and character lore RAG tools for ToolRegistry."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from modules.common.persona_scope import get_active_persona, set_active_persona

logger = logging.getLogger("agent.tools.persona")


class PersonaToolsMixin:
    """Native persona management and lore search tools for Agent Core."""

    persona_manager: Any
    apply_persona_fn: Optional[Callable[[str, str], Dict[str, Any]]]

    def _get_persona_manager(self) -> Any:
        mgr = getattr(self, "persona_manager", None)
        if mgr is not None:
            return mgr
        try:
            from modules.ai_provider.services.persona_rag import PersonaManager

            mgr = PersonaManager()
            self.persona_manager = mgr
            return mgr
        except Exception:
            return None

    def set_persona(self, name: str, response_language: str = "") -> str:
        target = str(name or "").strip()
        lang_ovr = str(response_language or "").strip().lower()
        if not target:
            return "Error: persona name cannot be empty."

        fn = getattr(self, "apply_persona_fn", None)
        if callable(fn):
            try:
                res = fn(target, lang_ovr)
                pid = str(res.get("persona") or target)
                disp = str(res.get("display_name") or pid)
                lang_note = f" (response_language={res.get('response_language')})" if res.get("response_language") else ""
                return f"Active persona switched to '{pid}' ({disp}){lang_note}."
            except Exception as exc:
                return f"Failed to switch persona to '{target}': {exc}"

        mgr = self._get_persona_manager()
        if mgr is None:
            return "Error: PersonaManager unavailable."
        try:
            loaded = mgr.load_persona(target)
            pid = str(loaded["name"])
            manifest = dict(loaded.get("manifest") or {})
            if lang_ovr:
                manifest["response_language"] = lang_ovr
            set_active_persona(pid, meta=manifest)
            return f"Active persona switched to '{pid}' ({manifest.get('display_name', pid)})."
        except Exception as exc:
            return f"Failed to switch persona to '{target}': {exc}"

    def list_personas(self) -> str:
        mgr = self._get_persona_manager()
        if mgr is None:
            return "Error: PersonaManager unavailable."
        active = get_active_persona()
        items = mgr.list_personas()
        if not items:
            return f"Active persona: {active}. No persona directories found."
        lines = [f"Active persona: {active}"]
        for item in items:
            pid = str(item.get("id") or "")
            marker = " *" if pid == active else ""
            disp = str(item.get("display_name") or pid)
            lines.append(f"- {pid}{marker} ({disp})")
        return "\n".join(lines)

    def search_persona_knowledge(self, query: str, limit: int = 3) -> str:
        q = str(query or "").strip()
        if not q:
            return "Error: query cannot be empty."
        mgr = self._get_persona_manager()
        if mgr is None:
            return "Persona lore store unavailable."
        active = get_active_persona()
        try:
            rag = mgr.get_rag(active)
            hits = rag.recall(q, limit=max(1, min(6, int(limit or 3))))
        except Exception as exc:
            return f"Persona lore search failed: {exc}"
        if not hits:
            return f"No specific lore entries found for '{q}' under persona '{active}'."
        lines = [f"Persona lore hits ({active}):"]
        for h in hits:
            title = f"[{h['title']}] " if h.get("title") else ""
            lines.append(f"- {title}{h.get('text', '')}")
        return "\n".join(lines)


__all__ = ["PersonaToolsMixin"]
