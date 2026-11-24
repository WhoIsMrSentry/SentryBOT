from __future__ import annotations

import inspect
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.common.ollama_compat import call_ollama_chat, chat_accepts_kwarg

from .agent_provider_parser import (
    build_provider_tool_instruction,
    parse_provider_tool_call,
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
    _FIRST_CLAUSE_SPLIT_RE: Optional[re.Pattern] = None

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

    @staticmethod
    def _has_unclosed_paren(text: str) -> bool:
        return text.count("(") > text.count(")")

    def _extract_ready_sentences(
        self,
        buffer: str,
        *,
        is_first_chunk: bool = False,
        allow_first_clause_split: bool = True,
    ) -> Tuple[List[str], str]:
        if not buffer:
            return [], ""
        if AgentStreamingMixin._SENTENCE_END_RE is None:
            AgentStreamingMixin._SENTENCE_END_RE = re.compile(r"([.!?…\n]+)")
        if AgentStreamingMixin._FIRST_CLAUSE_SPLIT_RE is None:
            AgentStreamingMixin._FIRST_CLAUSE_SPLIT_RE = re.compile(r"([,;:—–\n]+|[.!?…]+)")

        # Wait for closing ')' on stage-direction/parenthetical prefixes before emitting a split fragment
        if len(buffer) < 240 and self._has_unclosed_paren(buffer):
            return [], buffer

        # Ultra low-latency first clause break (disabled during bridge translation to avoid literal fragments)
        if is_first_chunk and allow_first_clause_split:
            words = buffer.split()
            if len(words) >= 2 or len(buffer) >= 12:
                parts = AgentStreamingMixin._FIRST_CLAUSE_SPLIT_RE.split(buffer)
                if len(parts) > 1:
                    first_clause = (parts[0] + parts[1]).strip()
                    if (
                        not self._has_unclosed_paren(first_clause)
                        and len(first_clause.split()) >= 1
                        and len(first_clause) >= 4
                    ):
                        remainder = "".join(parts[2:]).lstrip()
                        return [first_clause], remainder

        parts = AgentStreamingMixin._SENTENCE_END_RE.split(buffer)
        if len(parts) <= 1:
            return [], buffer

        sentences: List[str] = []
        i = 0
        while i < len(parts) - 1:
            chunk = parts[i] + parts[i + 1]
            if self._has_unclosed_paren(chunk) and i + 2 < len(parts):
                parts[i + 2] = chunk + parts[i + 2]
                i += 2
                continue
            c_clean = chunk.strip()
            if c_clean:
                sentences.append(c_clean)
            i += 2

        remainder = parts[-1] if len(parts) % 2 == 1 else ""
        return sentences, remainder

    @staticmethod
    def _chat_accepts_priority(client: Any) -> bool:
        return chat_accepts_kwarg(client, "priority")

    def _chat_maybe_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        on_sentence: Optional[Callable[..., None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        if callable(cancel_check) and cancel_check():
            return {"message": {"role": "assistant", "content": ""}, "cancelled": True}
        if not on_sentence:
            return self._chat_turn(model, messages, tools, options)
        if getattr(self, "llm_provider", "ollama") != "ollama":
            return self._chat_turn(model, messages, tools, options)
        # Enable streaming when on_sentence callback is provided unless explicitly forced off
        if getattr(self, "persona_stream_enabled", None) is False:
            return self._chat_turn(model, messages, tools, options)
        return self._stream_turn_sentence_by_sentence(
            model,
            messages,
            tools,
            options,
            on_sentence=on_sentence,
            cancel_check=cancel_check,
        )

    def _stream_turn_sentence_by_sentence(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        on_sentence: Optional[Callable[..., None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        if callable(cancel_check) and cancel_check():
            return {"message": {"role": "assistant", "content": ""}, "cancelled": True}
        if not on_sentence:
            return self._chat_turn(model, messages, tools, options)

        runtime_model = self._pick_runtime_model(model)
        full_text: List[str] = []
        thinking_parts: List[str] = []
        collected_tool_calls: List[Dict[str, Any]] = []
        buffer: str = ""
        first_token_ts: Optional[float] = None
        t0 = time.time()
        sentence_idx = 0
        is_first_chunk = True
        emitted_any = False
        done_reason = ""
        eval_count = 0

        def _emit(s: str) -> None:
            nonlocal sentence_idx, is_first_chunk, emitted_any
            emitted_any = True
            try:
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
            is_first_chunk = False

        try:
            stream_kwargs: Dict[str, Any] = {
                "model": runtime_model,
                "messages": messages,
                "stream": True,
            }
            if tools:
                stream_kwargs["tools"] = tools
            if options:
                stream_kwargs["options"] = options
            ollama_think = getattr(self, "ollama_think", None)
            if ollama_think is not None:
                stream_kwargs["think"] = ollama_think
            ollama_keep_alive = getattr(self, "ollama_keep_alive", None)
            if ollama_keep_alive is not None:
                stream_kwargs["keep_alive"] = ollama_keep_alive
            if self._chat_accepts_priority(self.ollama_client):
                stream_kwargs["priority"] = 0

            stream = call_ollama_chat(self.ollama_client, **stream_kwargs)
            for chunk in stream:
                if callable(cancel_check) and cancel_check():
                    close_fn = getattr(stream, "close", None)
                    if callable(close_fn):
                        try:
                            close_fn()
                        except Exception:
                            pass
                    return {"message": {"role": "assistant", "content": ""}, "cancelled": True}
                if first_token_ts is None:
                    first_token_ts = time.time()
                chunk_done_reason = (
                    chunk.get("done_reason") if isinstance(chunk, dict) else getattr(chunk, "done_reason", None)
                )
                if chunk_done_reason:
                    done_reason = str(chunk_done_reason)
                chunk_eval = chunk.get("eval_count") if isinstance(chunk, dict) else getattr(chunk, "eval_count", None)
                if chunk_eval is not None:
                    try:
                        eval_count = max(eval_count, int(chunk_eval))
                    except (TypeError, ValueError):
                        pass
                msg_chunk = chunk.get("message", {}) if isinstance(chunk, dict) else {}
                if not msg_chunk and hasattr(chunk, "message"):
                    raw_msg = getattr(chunk, "message")
                    msg_chunk = raw_msg if isinstance(raw_msg, dict) else {
                        "content": getattr(raw_msg, "content", ""),
                        "thinking": getattr(raw_msg, "thinking", ""),
                        "tool_calls": getattr(raw_msg, "tool_calls", None),
                    }
                chunk_thinking = msg_chunk.get("thinking", "")
                if chunk_thinking:
                    thinking_parts.append(str(chunk_thinking))
                chunk_calls = msg_chunk.get("tool_calls") or []
                if chunk_calls:
                    collected_tool_calls.extend(chunk_calls)
                content = msg_chunk.get("content", "")
                if not content:
                    continue
                full_text.append(content)
                if not collected_tool_calls or emitted_any:
                    buffer += content
                    allow_clause = not bool(getattr(self, "_active_bridge_translation", False))
                    sentences, buffer = self._extract_ready_sentences(
                        buffer,
                        is_first_chunk=is_first_chunk,
                        allow_first_clause_split=allow_clause,
                    )
                    for sentence in sentences:
                        _emit(sentence)

            if callable(cancel_check) and cancel_check():
                return {"message": {"role": "assistant", "content": ""}, "cancelled": True}

            if not collected_tool_calls or emitted_any:
                rem = buffer.strip()
                if rem:
                    _emit(rem)

            final_content = "".join(full_text)
            msg_out: Dict[str, Any] = {
                "role": "assistant",
                "content": final_content,
            }
            if thinking_parts:
                msg_out["thinking"] = "".join(thinking_parts)
            if collected_tool_calls:
                msg_out["tool_calls"] = collected_tool_calls
            out: Dict[str, Any] = {
                "message": msg_out,
                "latency": {
                    "ttft_ms": int((first_token_ts - t0) * 1000) if first_token_ts else 0,
                    "total_ms": int((time.time() - t0) * 1000),
                },
            }
            if done_reason:
                out["done_reason"] = done_reason
            if eval_count > 0:
                out["eval_count"] = eval_count
            return out
        except Exception as exc:
            if callable(cancel_check) and cancel_check():
                return {"message": {"role": "assistant", "content": ""}, "cancelled": True}
            is_transport = getattr(self, "_is_provider_transport_error", None)
            if first_token_ts is None and callable(is_transport) and is_transport(exc):
                raise
            logger.warning("Streaming chat failed, falling back to sync: %s", exc)
            return self._chat_turn(model, messages, tools, options)
