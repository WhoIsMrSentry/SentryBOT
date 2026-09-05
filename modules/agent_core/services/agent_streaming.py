from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .agent_provider_parser import (
    build_provider_tool_instruction,
    loads_first_json_object,
    parse_provider_tool_call,
    strip_code_fence,
)

logger = logging.getLogger("agent.orchestrator")


class AgentStreamingMixin:
    """Sentence-by-sentence streaming parser and runtime model selector."""

    ollama_client: Any
    provider_client: Any
    llm_provider: str
    clm_fallback_enabled: bool
    clm_fallback_model: str
    fallback_on_missing_model: bool
    persona_stream_enabled: bool
    _cached_model_names: List[str]
    _cached_model_names_ts: float

    _SENTENCE_END_RE: Optional[re.Pattern] = None

    def _build_provider_tool_instruction(self, tools: List[Dict[str, Any]]) -> str:
        return build_provider_tool_instruction(tools)

    def _parse_provider_tool_call(self, content: str, tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return parse_provider_tool_call(content, tools)

    def _list_ollama_models(self) -> List[str]:
        now = time.time()
        if now - self._cached_model_names_ts < 30.0 and self._cached_model_names:
            return list(self._cached_model_names)

        names: List[str] = []
        if self.ollama_client is not None and hasattr(self.ollama_client, "list"):
            try:
                raw = self.ollama_client.list()
                items = raw.get("models", []) if isinstance(raw, dict) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if name:
                        names.append(name)
            except Exception:
                names = []

        self._cached_model_names = names
        self._cached_model_names_ts = now
        return list(names)

    def _pick_runtime_model(self, preferred_model: str) -> str:
        model = str(preferred_model or "").strip()
        if self.llm_provider != "ollama":
            return model

        if not self.clm_fallback_enabled or not self.fallback_on_missing_model:
            return model

        fallback = str(self.clm_fallback_model or "").strip()
        if not model or not fallback or fallback == model:
            return model

        available = self._list_ollama_models()
        if available and model not in available and fallback in available:
            logger.warning("Primary model '%s' is missing. Switching to fallback '%s'.", model, fallback)
            return fallback
        return model

    def _extract_ready_sentences(self, buffer: str) -> Tuple[List[str], str]:
        if not buffer:
            return [], ""
        if AgentStreamingMixin._SENTENCE_END_RE is None:
            AgentStreamingMixin._SENTENCE_END_RE = re.compile(r"([.!?â€¦\n]+)")

        parts = AgentStreamingMixin._SENTENCE_END_RE.split(buffer)
        if len(parts) <= 1:
            return [], buffer

        sentences: List[str] = []
        i = 0
        while i < len(parts) - 1:
            chunk = parts[i] + parts[i + 1]
            c_clean = chunk.strip()
            if c_clean:
                sentences.append(c_clean)
            i += 2

        remainder = parts[-1] if len(parts) % 2 == 1 else ""
        return sentences, remainder

    def _chat_maybe_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        on_sentence: Optional[Callable[..., None]] = None,
    ) -> Dict[str, Any]:
        if tools:
            # Native tool-calling must use the normal chat path so Ollama can return tool_calls.
            return self._chat_turn(model, messages, tools, options)
        if not on_sentence or not getattr(self, "persona_stream_enabled", False):
            return self._chat_turn(model, messages, tools, options)
        return self._stream_turn_sentence_by_sentence(model, messages, tools, options, on_sentence=on_sentence)

    def _stream_turn_sentence_by_sentence(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        on_sentence: Optional[Callable[..., None]] = None,
    ) -> Dict[str, Any]:
        if not on_sentence:
            return self._chat_turn(model, messages, tools, options)

        runtime_model = self._pick_runtime_model(model)
        full_text: List[str] = []
        buffer: str = ""
        first_token_ts: Optional[float] = None
        t0 = time.time()
        sentence_idx = 0

        def _emit(s: str) -> None:
            nonlocal sentence_idx
            try:
                import inspect
                sig = inspect.signature(on_sentence)
                if len(sig.parameters) >= 2:
                    on_sentence(s, sentence_idx)
                else:
                    on_sentence(s)
            except Exception:
                try:
                    on_sentence(s, sentence_idx)
                except Exception:
                    try:
                        on_sentence(s)
                    except Exception:
                        pass
            sentence_idx += 1

        try:
            stream_kwargs: Dict[str, Any] = {
                "model": runtime_model,
                "messages": messages,
                "stream": True,
            }
            if options:
                stream_kwargs["options"] = options
            ollama_think = getattr(self, "ollama_think", None)
            if ollama_think is not None:
                stream_kwargs["think"] = ollama_think
            ollama_keep_alive = getattr(self, "ollama_keep_alive", None)
            if ollama_keep_alive is not None:
                stream_kwargs["keep_alive"] = ollama_keep_alive

            stream = self.ollama_client.chat(**stream_kwargs)
            for chunk in stream:
                if first_token_ts is None:
                    first_token_ts = time.time()
                content = chunk.get("message", {}).get("content", "")
                if not content:
                    continue
                full_text.append(content)
                buffer += content
                sentences, buffer = self._extract_ready_sentences(buffer)
                for sentence in sentences:
                    _emit(sentence)

            rem = buffer.strip()
            if rem:
                _emit(rem)

            final_content = "".join(full_text)
            return {
                "message": {
                    "role": "assistant",
                    "content": final_content,
                },
                "latency": {
                    "ttft_ms": int((first_token_ts - t0) * 1000) if first_token_ts else 0,
                    "total_ms": int((time.time() - t0) * 1000),
                },
            }
        except Exception as exc:
            logger.warning("Streaming chat failed, falling back to sync: %s", exc)
            return self._chat_turn(model, messages, tools, options)
