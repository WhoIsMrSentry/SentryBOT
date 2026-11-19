"""Dynamic persona runtime, derived Ollama model selection, lore RAG, and isolated history."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from modules.common.model_roles import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_UTILITY_MODEL,
    explicit_single_model_mode,
)
from modules.common.persona_scope import (
    DEFAULT_PERSONA_ID,
    get_active_persona,
    normalize_persona_id,
    register_persona_listener,
    set_active_persona,
)

logger = logging.getLogger("agent.persona")


class AgentPersonaMixin:
    """Manages active character persona, derived Ollama model, RAG lore, TTS voice, and isolated history."""

    config: Dict[str, Any]
    chat_history: List[Dict[str, Any]]
    persona_system_prompt: str

    def _init_persona_runtime(self, config: Dict[str, Any], *, configured_prompt: str = "") -> None:
        agent_cfg = config.get("agent", {}) if isinstance(config.get("agent"), dict) else {}
        base_dir = str(agent_cfg.get("personalities_dir") or "modules/ai_provider/config/personalities")
        self._configured_sentry_prompt = str(configured_prompt or "").strip()
        self.active_persona: str = normalize_persona_id(
            agent_cfg.get("persona") or agent_cfg.get("default_persona") or get_active_persona()
        )
        self.active_persona_meta: Dict[str, Any] = {}
        self.active_persona_model: str = DEFAULT_CHAT_MODEL
        self.active_persona_base_model: str = DEFAULT_UTILITY_MODEL
        self.active_persona_rag: Any = None
        self._persona_histories: Dict[str, List[Dict[str, Any]]] = {}
        self._persona_response_language: str = "follow_user"
        self._auto_created_models: set[str] = set()
        self.persona_manager: Any = None
        try:
            from modules.ai_provider.services.persona_rag import PersonaManager

            self.persona_manager = PersonaManager(base_dir)
            if any(p.get("id") == self.active_persona for p in self.persona_manager.list_personas()):
                self.apply_persona(
                    self.active_persona,
                    notify=False,
                    trigger_emotion=False,
                )
        except Exception as exc:
            logger.debug("Persona runtime initialized without filesystem manager: %s", exc)

        if not getattr(self, "_persona_listener_bound", False):
            self._persona_listener_cb = self._on_global_persona_change
            register_persona_listener(self._persona_listener_cb)
            self._persona_listener_bound = True

    def _on_global_persona_change(self, persona_id: str, meta: Dict[str, Any]) -> None:
        if getattr(self, "_applying_persona_guard", False):
            return
        resp_lang = str(meta.get("response_language") or "") if isinstance(meta, dict) else ""
        try:
            self.apply_persona(
                persona_id,
                response_language=resp_lang,
                notify=False,
                trigger_emotion=False,
            )
        except Exception as exc:
            logger.debug("Global persona listener sync skipped for '%s': %s", persona_id, exc)

    def _sync_persona_history(self, new_pid: str) -> None:
        prev_pid = normalize_persona_id(getattr(self, "active_persona", DEFAULT_PERSONA_ID))
        if prev_pid == new_pid:
            return
        histories = getattr(self, "_persona_histories", None)
        if not isinstance(histories, dict):
            histories = {}
            self._persona_histories = histories
        lock_fn = getattr(self, "_ensure_history_lock", None)
        lock = lock_fn() if callable(lock_fn) else None
        if lock is not None:
            with lock:
                histories[prev_pid] = [dict(m) for m in getattr(self, "chat_history", [])]
                self.chat_history = [dict(m) for m in histories.get(new_pid, [])]
        else:
            histories[prev_pid] = [dict(m) for m in getattr(self, "chat_history", [])]
            self.chat_history = [dict(m) for m in histories.get(new_pid, [])]

    def apply_persona(
        self,
        name: str,
        response_language: str = "",
        *,
        notify: bool = True,
        trigger_emotion: bool = True,
        ensure_remote_model: bool = False,
    ) -> Dict[str, Any]:
        """Switch active persona prompt, derived Ollama model, RAG index, response language, and isolated history."""
        mgr = getattr(self, "persona_manager", None)
        if mgr is None:
            from modules.ai_provider.services.persona_rag import PersonaManager

            mgr = PersonaManager()
            self.persona_manager = mgr

        loaded = mgr.load_persona(name)
        new_pid = normalize_persona_id(loaded["name"])
        manifest = dict(loaded.get("manifest") or {})
        lang_override = str(response_language or "").strip().lower()
        effective_lang = lang_override or str(manifest.get("response_language") or "follow_user").strip().lower()
        manifest["response_language"] = effective_lang

        derived_model = str(manifest.get("model") or f"{new_pid}:latest").strip()
        base_model = str(manifest.get("base_model") or DEFAULT_UTILITY_MODEL).strip()

        self._applying_persona_guard = True
        try:
            self._sync_persona_history(new_pid)
            self.active_persona = new_pid
            self.active_persona_meta = manifest
            self.active_persona_model = derived_model
            self.active_persona_base_model = base_model
            self.active_persona_rag = loaded.get("rag")
            self._persona_response_language = effective_lang

            if new_pid == DEFAULT_PERSONA_ID and getattr(self, "_configured_sentry_prompt", ""):
                self.persona_system_prompt = self._configured_sentry_prompt
            else:
                self.persona_system_prompt = str(loaded.get("prompt_text") or "").strip()

            set_active_persona(new_pid, meta=manifest, notify=notify)
        finally:
            self._applying_persona_guard = False

        if ensure_remote_model and new_pid != DEFAULT_PERSONA_ID:
            self._ensure_active_persona_model_on_remote(new_pid, derived_model)

        if trigger_emotion:
            default_emotion = str(manifest.get("default_emotion") or "").strip().lower()
            reg = getattr(self, "tool_registry", None)
            if default_emotion and reg is not None and hasattr(reg, "express_emotion"):
                try:
                    reg.express_emotion(default_emotion, intensity=0.55)
                except Exception:
                    pass

        return self.get_persona_state()

    def create_persona(
        self,
        name: str,
        instructions: str,
        *,
        urls: Optional[List[str]] = None,
        base_model: str = DEFAULT_UTILITY_MODEL,
        display_name: str = "",
        response_language: str = "follow_user",
        tts_voice: Optional[str] = None,
        tts_voice_en: Optional[str] = None,
        default_emotion: str = "neutral",
        aliases: Optional[List[str]] = None,
        create_model: bool = True,
        fetch_urls: bool = True,
        activate: bool = True,
    ) -> Dict[str, Any]:
        """Create a new persona derived from `nemotron-3.5-bolt:e4b`, build its RAG, and push to remote Ollama."""
        mgr = getattr(self, "persona_manager", None)
        if mgr is None:
            from modules.ai_provider.services.persona_rag import PersonaManager

            mgr = PersonaManager()
            self.persona_manager = mgr

        base_url = str(getattr(self, "ollama_base_url", "") or "").strip()
        if not base_url:
            cfg = getattr(self, "config", None) or {}
            base_url = str(
                (cfg.get("ollama") or {}).get("base_url")
                or (cfg.get("agent") or {}).get("ollama_base_url")
                or ""
            ).strip()

        res = mgr.create_persona(
            name,
            instructions,
            urls=urls,
            base_model=base_model,
            display_name=display_name,
            response_language=response_language,
            tts_voice=tts_voice,
            tts_voice_en=tts_voice_en,
            default_emotion=default_emotion,
            aliases=aliases,
            create_model=create_model,
            ollama_base_url=base_url,
            fetch_urls=fetch_urls,
        )
        if activate:
            res["state"] = self.apply_persona(
                res["persona"],
                response_language=response_language,
                trigger_emotion=False,
            )
        return res

    def get_persona_state(self) -> Dict[str, Any]:
        pid = normalize_persona_id(getattr(self, "active_persona", None) or get_active_persona())
        rag = getattr(self, "active_persona_rag", None)
        rag_stats = rag.stats() if rag is not None and hasattr(rag, "stats") else {}
        return {
            "ok": True,
            "persona": pid,
            "model": str(getattr(self, "active_persona_model", f"{pid}:latest")),
            "base_model": str(getattr(self, "active_persona_base_model", DEFAULT_UTILITY_MODEL)),
            "display_name": str((getattr(self, "active_persona_meta", None) or {}).get("display_name") or pid),
            "response_language": str(getattr(self, "_persona_response_language", "follow_user") or "follow_user"),
            "meta": dict(getattr(self, "active_persona_meta", None) or {}),
            "rag": rag_stats,
        }

    def _get_persona_lore_context(self, query: str, *, limit: int = 3) -> str:
        rag = getattr(self, "active_persona_rag", None)
        q = str(query or "").strip()
        if rag is None or not q or not hasattr(rag, "build_prompt_context"):
            return ""
        try:
            return str(rag.build_prompt_context(q, limit=limit) or "").strip()
        except Exception as exc:
            logger.debug("Persona RAG lookup skipped: %s", exc)
            return ""

    def effective_tts_voice(self, target_lang: str) -> Optional[str]:
        """Resolve Piper voice override from the active persona manifest when configured."""
        meta = getattr(self, "active_persona_meta", None) or {}
        if not isinstance(meta, dict):
            return None
        explicit = str(meta.get("tts_voice") or "").strip()
        if explicit and explicit.lower() not in {"auto", "none", "null"}:
            return explicit
        if str(target_lang or "").strip().lower() == "en":
            en_voice = str(meta.get("tts_voice_en") or "").strip()
            if en_voice and en_voice.lower() not in {"auto", "none", "null"}:
                return en_voice
        return None

    @staticmethod
    def _model_present(model_name: str, available: List[str]) -> bool:
        target = str(model_name or "").strip().lower()
        bare = target.split(":", 1)[0]
        for item in available:
            low = str(item or "").strip().lower()
            if low == target or (target.endswith(":latest") and low == bare):
                return True
        return False

    def _ensure_active_persona_model_on_remote(self, persona_id: str, model_name: str) -> bool:
        mgr = getattr(self, "persona_manager", None)
        if mgr is None or not hasattr(mgr, "ensure_ollama_model"):
            return False
        attempted = getattr(self, "_auto_created_models", None)
        if isinstance(attempted, set) and model_name in attempted:
            return False
        if isinstance(attempted, set):
            attempted.add(model_name)
        base_url = str(getattr(self, "ollama_base_url", "") or "").strip()
        if not base_url:
            cfg = getattr(self, "config", None) or {}
            base_url = str(
                (cfg.get("ollama") or {}).get("base_url")
                or (cfg.get("agent") or {}).get("ollama_base_url")
                or ""
            ).strip()
        if not base_url:
            return False
        try:
            res = mgr.ensure_ollama_model(persona_id, base_url=base_url)
            if res.get("ok"):
                self._cached_model_names_ts = 0.0
                return True
        except Exception as exc:
            logger.debug("Auto-create remote model '%s' skipped: %s", model_name, exc)
        return False

    def _resolve_non_sentry_model(self, candidate: str, fallback: str = DEFAULT_UTILITY_MODEL) -> str:
        """Select each persona's derived Ollama model (e.g. `glados:latest` from `nemotron-3.5-bolt:e4b`)."""
        active_pid = normalize_persona_id(getattr(self, "active_persona", None) or get_active_persona())
        if active_pid == DEFAULT_PERSONA_ID:
            return candidate
        if explicit_single_model_mode(getattr(self, "config", None)) is True:
            return candidate

        meta = getattr(self, "active_persona_meta", None) or {}
        target = str(
            getattr(self, "active_persona_model", "")
            or meta.get("model")
            or f"{active_pid}:latest"
        ).strip()
        base_fallback = str(
            getattr(self, "active_persona_base_model", "")
            or meta.get("base_model")
            or fallback
            or DEFAULT_UTILITY_MODEL
        ).strip()

        list_fn = getattr(self, "_list_ollama_models", None)
        client = getattr(self, "ollama_client", None)
        if client is not None and callable(list_fn):
            try:
                available = list_fn()
                if available and not self._model_present(target, available):
                    if self._ensure_active_persona_model_on_remote(active_pid, target):
                        return target
                    logger.warning(
                        "Derived persona model '%s' not found on Ollama; using base model '%s' with persona prompt.",
                        target,
                        base_fallback,
                    )
                    return base_fallback
            except Exception:
                pass
        return target

    def _close_persona_runtime(self) -> None:
        mgr = getattr(self, "persona_manager", None)
        if mgr is not None and hasattr(mgr, "close"):
            try:
                mgr.close()
            except Exception:
                pass


__all__ = ["AgentPersonaMixin"]
