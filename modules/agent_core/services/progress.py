"""Staged execution progress system for SentryBOT Agent Core.

Provides immediate acknowledgement (100-500ms), plan summary,
tool start/done notifications, and final persona response events.

Progress events are forwarded to SpeechArbiter so the robot never
stays silent during long tool/VLM operations.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .tool_progress import plan_goal_should_speak, subagent_module_should_speak, tool_result_succeeded

logger = logging.getLogger("agent.progress")


# ── Progress event types ──────────────────────────────────────────────
PROGRESS_TYPES = frozenset({
    "ack",               # immediate acknowledgement
    "plan",              # plan summary
    "tool_start",        # tool execution started
    "tool_done",         # tool execution completed
    "tool_error",        # tool execution failed
    "vision_capture_done",  # camera frame captured
    "vlm_processing",    # VLM inference in progress
    "final",             # final persona response ready
    "status",            # generic status
    "subagent_start",    # sub-agent started
    "subagent_done",     # sub-agent completed
    "persona_start",     # persona synthesis started
    "arbiter_status",    # periodic arbiter snapshot for admin UI
})


# ── Multi-language message catalog (YAML, no hardcoded languages) ─────
_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "progress_messages.yml"
_catalog_cache: Optional[Dict[str, Any]] = None


def _load_catalog() -> Dict[str, Any]:
    """Load the progress message catalog once (lazy, cached)."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    data: Dict[str, Any] = {}
    try:
        import yaml

        with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        if isinstance(loaded, dict):
            data = loaded
    except Exception as exc:  # pragma: no cover - IO/environment specific
        logger.warning("Progress message catalog load failed: %s", exc)
    if not isinstance(data.get("languages"), dict):
        data["languages"] = {"en": {"ack": ["Okay."], "persona_start": "Putting the answer together."}}
    data.setdefault("default_language", "en")
    _catalog_cache = data
    return data


def _catalog_lang(lang: str) -> Dict[str, Any]:
    catalog = _load_catalog()
    languages = catalog.get("languages", {})
    entry = languages.get(str(lang or "").strip().lower())
    if isinstance(entry, dict):
        return entry
    fallback = languages.get(str(catalog.get("default_language", "en")))
    return fallback if isinstance(fallback, dict) else {}


def _msg(lang: str, key: str, default: str = "") -> str:
    """Fetch a single message for a language, falling back to default language."""
    entry = _catalog_lang(lang)
    value = entry.get(key)
    if isinstance(value, str) and value.strip():
        return value
    default_entry = _catalog_lang("")
    value = default_entry.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return default

def _msg_choice(lang: str, key: str) -> str:
    entry = _catalog_lang(lang)
    values = entry.get(key)
    if not (isinstance(values, list) and values):
        values = _catalog_lang("").get(key)
    if isinstance(values, list) and values:
        return str(random.choice(values))
    return ""


def _msg_map(lang: str, key: str) -> Dict[str, str]:
    entry = _catalog_lang(lang)
    values = entry.get(key)
    if not isinstance(values, dict):
        values = _catalog_lang("").get(key)
    return values if isinstance(values, dict) else {}


def supported_progress_languages() -> List[str]:
    return sorted(_load_catalog().get("languages", {}).keys())


class ProgressManager:
    """Manages staged execution progress with TTS forwarding.

    Usage::

        pm = ProgressManager(speech_arbiter=arbiter)
        token = pm.new_request()

        pm.emit_ack(token)         # immediate 100-500ms
        pm.emit_plan(token, [...]) # plan summary
        pm.emit_tool_start(token, "get_vision")
        pm.emit_tool_done(token, "get_vision")
        pm.emit_final(token)       # cancel stale, mark done
    """

    def __init__(
        self,
        speech_arbiter: Optional[Any] = None,
        speak_fn: Optional[Callable[..., Any]] = None,
        persona_start_min_elapsed_s: float = 4.0,
        interaction_emit_fn: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> None:
        self._speech_arbiter = speech_arbiter
        self._speak_fn = speak_fn
        self._interaction_emit_fn = interaction_emit_fn
        self._persona_start_min_elapsed_s = float(persona_start_min_elapsed_s)
        self._active_tokens: Dict[str, float] = {}  # token -> created_at
        self._token_languages: Dict[str, str] = {}  # token -> session language (tr|en)
        self._last_progress_text: Dict[str, str] = {}  # token -> last spoken text
        self._latest_event: Dict[str, Any] = {}
        # Optional arbiter references injected after construction.
        self._action_arbiter: Optional[Any] = None
        self._vision_arbiter: Optional[Any] = None
        self._expression_arbiter: Optional[Any] = None
        self._tool_execution_arbiter: Optional[Any] = None

    def attach_arbiters(
        self,
        *,
        action_arbiter: Optional[Any] = None,
        vision_arbiter: Optional[Any] = None,
        expression_arbiter: Optional[Any] = None,
        tool_execution_arbiter: Optional[Any] = None,
    ) -> None:
        """Wire arbiter references so :meth:`arbiter_snapshot` can read them."""
        if action_arbiter is not None:
            self._action_arbiter = action_arbiter
        if vision_arbiter is not None:
            self._vision_arbiter = vision_arbiter
        if expression_arbiter is not None:
            self._expression_arbiter = expression_arbiter
        if tool_execution_arbiter is not None:
            self._tool_execution_arbiter = tool_execution_arbiter

    def arbiter_snapshot(self) -> Dict[str, Any]:
        """Build a defensive snapshot of every arbiter status.

        Designed for SSE feeds and admin dashboards. Missing arbiters simply
        report ``{}`` instead of raising, so the snapshot keeps working in
        degraded environments.
        """
        out: Dict[str, Any] = {"timestamp": time.time()}
        try:
            out["action"] = self._action_arbiter.get_exclusive_status() if self._action_arbiter else {}
        except Exception:
            out["action"] = {}
        try:
            out["speech"] = self._speech_arbiter.get_status() if self._speech_arbiter and hasattr(self._speech_arbiter, "get_status") else {}
        except Exception:
            out["speech"] = {}
        try:
            out["vision"] = self._vision_arbiter.status() if self._vision_arbiter else {}
        except Exception:
            out["vision"] = {}
        try:
            out["expression"] = self._expression_arbiter.status() if self._expression_arbiter else {}
        except Exception:
            out["expression"] = {}
        try:
            out["tool_execution"] = self._tool_execution_arbiter.get_status() if self._tool_execution_arbiter else {}
        except Exception:
            out["tool_execution"] = {}
        return out

    def set_speech_arbiter(self, arbiter: Any) -> None:
        self._speech_arbiter = arbiter

    def new_request(self, language: str = "tr") -> str:
        """Create a new cancel token for a request lifecycle."""
        import uuid
        token = uuid.uuid4().hex[:10]
        self._active_tokens[token] = time.time()
        # Keep the bare 2-letter code; the catalog decides which languages exist.
        lang = str(language or "tr").strip().lower()[:2] or "tr"
        self._token_languages[token] = lang
        return token

    def _lang_for(self, token: str) -> str:
        return self._token_languages.get(token, "tr")

    def is_active(self, token: str) -> bool:
        return token in self._active_tokens

    def _emit_interaction(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self._interaction_emit_fn:
            return
        try:
            self._interaction_emit_fn(event_type, data or {})
        except Exception as exc:
            logger.debug("interaction emit failed: %s", exc)

    # ── Stage 1: Immediate Ack ────────────────────────────────────────
    def emit_ack(self, token: str, custom_text: str = "", *, speak: bool = True) -> None:
        """Emit an immediate acknowledgement (template-based, no LLM)."""
        self._emit_interaction("agent.processing.start", {"stage": "ack"})
        if not speak:
            return
        text = custom_text or _msg_choice(self._lang_for(token), "ack")
        self._speak_progress(token, text, event_type="ack")

    # ── Stage 2: Plan Summary ────────────────────────────────────────
    def emit_plan(self, token: str, plan: List[Dict[str, str]]) -> None:
        """Emit a brief plan summary."""
        if not plan:
            return
        # Build a short natural summary
        parts = []
        for step in plan[:3]:
            goal = step.get("goal", "")
            if goal and plan_goal_should_speak(goal):
                parts.append(goal)
        if parts:
            prefix = _msg(self._lang_for(token), "plan_prefix", "My plan: ")
            summary = prefix + ", ".join(parts[:2]) + "."
            self._speak_progress(token, summary, event_type="plan")

    # ── Stage 3: Tool Progress ───────────────────────────────────────
    def emit_tool_start(self, token: str, tool_name: str) -> None:
        # Do not speak before execution — static lines must match real tool outcomes.
        logger.debug("tool_start %s (no TTS until success)", tool_name)

    def emit_tool_done(self, token: str, tool_name: str, result: str = "") -> None:
        if not tool_result_succeeded(tool_name, result):
            logger.debug("tool_done %s skipped TTS (no usable result)", tool_name)
            return
        text = _msg_map(self._lang_for(token), "tool_done").get(tool_name)
        if text:
            self._speak_progress(token, text, event_type="tool_done")

    def emit_tool_error(self, token: str, tool_name: str, error: str = "") -> None:
        template = _msg(self._lang_for(token), "tool_error", "There was a problem while running {tool}.")
        self._speak_progress(token, template.format(tool=tool_name), event_type="tool_error")

    def emit_vlm_processing(self, token: str) -> None:
        text = _msg_choice(self._lang_for(token), "vlm_processing")
        if text:
            self._speak_progress(token, text, event_type="vlm_processing")

    def emit_vision_capture(self, token: str) -> None:
        text = _msg(self._lang_for(token), "vision_capture", "Image captured, processing now.")
        self._speak_progress(token, text, event_type="vision_capture_done")

    # ── Stage 4: Final ───────────────────────────────────────────────
    def emit_final(self, token: str) -> None:
        """Mark request as final – cancel all stale progress messages."""
        self._emit_interaction("agent.processing.end", {"token": token})
        self._cancel_stale(token)
        self._active_tokens.pop(token, None)
        self._token_languages.pop(token, None)
        self._last_progress_text.pop(token, None)

    def cancel_stale(self, token: str = "") -> None:
        """Cancel stale progress messages for a specific token or all."""
        self._cancel_stale(token)

    # ── Raw progress callback (for Agent Core integration) ────────────
    def _handle_progress_status(self, event, token):
        text = str(event.get("text", "")).strip()
        if text:
            self._speak_progress(token, text, event_type="status")

    def _handle_progress_tool_done(self, event, token):
        tool = str(event.get("tool", "")).strip()
        if tool and token:
            self.emit_tool_done(token, tool, str(event.get("result", "")))

    def _handle_progress_tool_error(self, event, token):
        tool = str(event.get("tool", "")).strip()
        error = str(event.get("error", "")).strip()
        if token:
            self.emit_tool_error(token, tool, error)

    def _handle_progress_plan(self, event, token):
        plan = event.get("plan", [])
        if isinstance(plan, list) and token:
            self.emit_plan(token, plan)

    def _handle_progress_subagent_start(self, event, token):
        module = str(event.get("module", "")).strip()
        if module and token and subagent_module_should_speak(module):
            template = _msg(self._lang_for(token), "subagent_start", "Running the {module} module.")
            self._speak_progress(token, template.format(module=module), "subagent_start")

    def _handle_progress_subagent_done(self, event, token):
        pass

    def _handle_progress_persona_start(self, event, token):
        if not token:
            return
        # Only speak the "putting the answer together" filler when the request
        # has already been running long enough to feel slow; quick turns should
        # go straight to the final answer.
        started = self._active_tokens.get(token)
        if started is not None and (time.time() - started) < self._persona_start_min_elapsed_s:
            return
        msg = _msg(self._lang_for(token), "persona_start", "Putting the answer together.")
        self._speak_progress(token, msg, "persona_start")

    _PROGRESS_HANDLER_NAMES = {
        "status": "_handle_progress_status",
        "tool_done": "_handle_progress_tool_done",
        "tool_error": "_handle_progress_tool_error",
        "plan": "_handle_progress_plan",
        "subagent_start": "_handle_progress_subagent_start",
        "subagent_done": "_handle_progress_subagent_done",
        "persona_start": "_handle_progress_persona_start",
    }

    def on_progress_event(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("type", "")).strip()
        token = str(event.get("token", "")).strip()
        self._latest_event = {"timestamp": time.time(), "token": token, "event": dict(event)}
        handler_name = self._PROGRESS_HANDLER_NAMES.get(event_type)
        if handler_name:
            getattr(self, handler_name)(event, token)

    # ── Internal ──────────────────────────────────────────────────────
    def _speak_progress(self, token: str, text: str, event_type: str = "progress") -> None:
        if not text:
            return

        # Dedup: don't repeat the same text for the same token
        if token:
            last = self._last_progress_text.get(token, "")
            if last == text:
                return
            self._last_progress_text[token] = text

        # Route to SpeechArbiter if available
        if self._speech_arbiter is not None and hasattr(self._speech_arbiter, "enqueue_progress"):
            self._speech_arbiter.enqueue_progress(
                text, cancel_token=token, language=self._lang_for(token),
            )
            return

        # Fallback: direct speak_fn
        if self._speak_fn:
            try:
                self._speak_fn(text=text)
            except Exception as exc:
                logger.debug("Progress speak_fn failed: %s", exc)
            return

        logger.debug("Progress [%s]: %s", event_type, text)

    def _cancel_stale(self, token: str) -> None:
        if self._speech_arbiter is not None:
            if token and hasattr(self._speech_arbiter, "cancel_by_token"):
                self._speech_arbiter.cancel_by_token(token)
            elif hasattr(self._speech_arbiter, "cancel_progress"):
                self._speech_arbiter.cancel_progress()

    def get_latest_event(self) -> Dict[str, Any]:
        if not self._latest_event:
            return {}
        return dict(self._latest_event)


__all__ = ["ProgressManager", "PROGRESS_TYPES"]
