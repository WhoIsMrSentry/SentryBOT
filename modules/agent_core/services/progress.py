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


# ── Template-based immediate acks (no LLM needed) ────────────────────
_ACK_TEMPLATES_TR = [
    "Tamam, bakıyorum.",
    "Anladım, işleme alıyorum.",
    "Hemen kontrol ediyorum.",
    "Bir saniye, üzerinde çalışıyorum.",
]

_ACK_TEMPLATES_EN = [
    "Okay, let me check.",
    "Got it, working on that.",
    "One moment, I'm on it.",
    "Sure, give me a second.",
]

_TOOL_START_TEMPLATES_TR: Dict[str, str] = {
    "get_vision": "Görüş verisini alıyorum.",
    "get_visual_context": "Çevreyi inceliyorum, son görüntü önbelleğine bakıyorum.",
    "get_sensor_data": "Sensör verilerini okuyorum.",
    "search_memory": "Hafızamı tarıyorum.",
    "move_head": "Kafamı çeviriyorum.",
    "set_lights": "Işıkları ayarlıyorum.",
    "focus_person": "Kişiye odaklanıyorum.",
    "ask_vlm_about_scene": "Sahneyi analiz ediyorum.",
    "describe_scene": "Sahneyi yorumluyorum.",
    "remember_person": "Kişiyi hafızama kaydediyorum.",
}

_TOOL_DONE_TEMPLATES_TR: Dict[str, str] = {
    "get_vision": "Görüntüyü aldım.",
    "get_visual_context": "Görüntüyü aldım, şimdi kişileri kontrol ediyorum.",
    "get_sensor_data": "Sensör verileri geldi.",
    "search_memory": "Hafıza taraması tamamlandı.",
    "ask_vlm_about_scene": "Sahne analizi tamamlandı.",
}

_VLM_PROCESSING_TEMPLATES_TR = [
    "Görüntüyü işliyorum, biraz bekle.",
    "Sahneyi yorumluyorum.",
]

_TOOL_START_TEMPLATES_EN: Dict[str, str] = {
    "get_vision": "Fetching vision data.",
    "get_visual_context": "Checking the latest vision cache.",
    "get_sensor_data": "Reading sensor data.",
    "search_memory": "Searching my memory.",
    "move_head": "Turning my head.",
    "set_lights": "Adjusting the lights.",
    "focus_person": "Focusing on the person.",
    "ask_vlm_about_scene": "Analyzing the scene.",
    "describe_scene": "Describing what I see.",
    "remember_person": "Saving this person to memory.",
}

_TOOL_DONE_TEMPLATES_EN: Dict[str, str] = {
    "get_vision": "Image captured.",
    "get_visual_context": "Got the view, checking people now.",
    "get_sensor_data": "Sensor data received.",
    "search_memory": "Memory search complete.",
    "ask_vlm_about_scene": "Scene analysis complete.",
}

_VLM_PROCESSING_TEMPLATES_EN = [
    "Processing the image, one moment.",
    "Analyzing the scene.",
]


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
    ) -> None:
        self._speech_arbiter = speech_arbiter
        self._speak_fn = speak_fn
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
        lang = str(language or "tr").strip().lower()
        if lang.startswith("en"):
            lang = "en"
        elif lang.startswith("tr"):
            lang = "tr"
        else:
            lang = "tr"
        self._token_languages[token] = lang
        return token

    def _lang_for(self, token: str) -> str:
        return self._token_languages.get(token, "tr")

    def is_active(self, token: str) -> bool:
        return token in self._active_tokens

    # ── Stage 1: Immediate Ack ────────────────────────────────────────
    def emit_ack(self, token: str, custom_text: str = "") -> None:
        """Emit an immediate acknowledgement (template-based, no LLM)."""
        if custom_text:
            text = custom_text
        elif self._lang_for(token) == "en":
            text = random.choice(_ACK_TEMPLATES_EN)
        else:
            text = random.choice(_ACK_TEMPLATES_TR)
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
            if self._lang_for(token) == "en":
                summary = "My plan: " + ", ".join(parts[:2]) + "."
            else:
                summary = "Planım: " + ", ".join(parts[:2]) + "."
            self._speak_progress(token, summary, event_type="plan")

    # ── Stage 3: Tool Progress ───────────────────────────────────────
    def emit_tool_start(self, token: str, tool_name: str) -> None:
        # Do not speak before execution — static lines must match real tool outcomes.
        logger.debug("tool_start %s (no TTS until success)", tool_name)

    def emit_tool_done(self, token: str, tool_name: str, result: str = "") -> None:
        if not tool_result_succeeded(tool_name, result):
            logger.debug("tool_done %s skipped TTS (no usable result)", tool_name)
            return
        templates = _TOOL_DONE_TEMPLATES_EN if self._lang_for(token) == "en" else _TOOL_DONE_TEMPLATES_TR
        text = templates.get(tool_name)
        if text:
            self._speak_progress(token, text, event_type="tool_done")

    def emit_tool_error(self, token: str, tool_name: str, error: str = "") -> None:
        if self._lang_for(token) == "en":
            text = f"There was a problem while running {tool_name}."
        else:
            text = f"{tool_name} çalışırken bir sorun oldu."
        self._speak_progress(token, text, event_type="tool_error")

    def emit_vlm_processing(self, token: str) -> None:
        templates = _VLM_PROCESSING_TEMPLATES_EN if self._lang_for(token) == "en" else _VLM_PROCESSING_TEMPLATES_TR
        text = random.choice(templates)
        self._speak_progress(token, text, event_type="vlm_processing")

    def emit_vision_capture(self, token: str) -> None:
        if self._lang_for(token) == "en":
            text = "Image captured, processing now."
        else:
            text = "Görüntüyü aldım, şimdi işliyorum."
        self._speak_progress(token, text, event_type="vision_capture_done")

    # ── Stage 4: Final ───────────────────────────────────────────────
    def emit_final(self, token: str) -> None:
        """Mark request as final – cancel all stale progress messages."""
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
            msg = f"Running the {module} module." if self._lang_for(token) == "en" else f"{module} modülünü çalıştırıyorum."
            self._speak_progress(token, msg, "subagent_start")

    def _handle_progress_subagent_done(self, event, token):
        pass

    def _handle_progress_persona_start(self, event, token):
        if token:
            msg = "Putting the answer together." if self._lang_for(token) == "en" else "Sonuçları birleştirip yanıt hazırlıyorum."
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
