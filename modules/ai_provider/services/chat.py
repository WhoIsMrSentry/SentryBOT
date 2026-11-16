from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, Iterator, List, Optional

from .clients import LLMClientProtocol
from .memory import ChatMemory
from .tags import extract_llm_tags

logger = logging.getLogger("ollama.chat")


class OllamaChatService:
    def __init__(
        self,
        client: LLMClientProtocol,
        persona_name: str = "sentry",
        max_history: int = 6,
        use_persona_as_model: bool = True,
        num_predict: int = 100,
    ) -> None:
        self.client = client
        self._lock = threading.RLock()
        self.persona_name = persona_name
        self.memory = ChatMemory(max_turns=max_history)
        self.use_persona_as_model = bool(use_persona_as_model)
        self.num_predict = int(num_predict)

    def set_num_predict(self, value: int) -> int:
        with self._lock:
            self.num_predict = max(48, int(value))
            return self.num_predict

    def update_persona(self, persona_name: str, use_persona_as_model: Optional[bool] = None) -> None:
        with self._lock:
            self.persona_name = str(persona_name)
            if use_persona_as_model is not None:
                self.use_persona_as_model = bool(use_persona_as_model)

    def _build_request(self, query: str, extra_history: Optional[List[Dict[str, str]]]) -> tuple[List[Dict[str, str]], Optional[str], Dict[str, Any]]:
        with self._lock:
            messages: List[Dict[str, str]] = []
            if extra_history:
                messages.extend(extra_history)
            messages.extend(self.memory.as_list())
            messages.append({"role": "user", "content": query})
            model_name = self.persona_name if self.use_persona_as_model else None
            options: Dict[str, Any] = {"num_predict": self.num_predict}
            return messages, model_name, options

    @staticmethod
    def _extract_raw_text(res: Any) -> str:
        if isinstance(res, dict):
            return str(res.get("message", {}).get("content", ""))
        if hasattr(res, "message"):
            return str(getattr(res.message, "content", ""))
        if hasattr(res, "model_dump"):
            return str(res.model_dump().get("message", {}).get("content", ""))
        return ""

    @staticmethod
    def _parse_response(raw_text: str, response_format: Optional[Any]) -> Dict[str, Any]:
        if response_format is not None:
            stripped = raw_text.strip()
            if stripped.startswith("{"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        text_val = str(parsed.get("text") or "").strip()
                        thoughts_val = str(parsed.get("thoughts") or "").strip()
                        actions_val = parsed.get("actions")
                        payload: Dict[str, Any] = {
                            "text": text_val or stripped,
                            "thoughts": thoughts_val,
                            "raw": raw_text,
                        }
                        if isinstance(actions_val, list) and actions_val:
                            payload["actions"] = actions_val
                        return payload
                except json.JSONDecodeError:
                    pass
        cleaned_text, actions = extract_llm_tags(raw_text)
        payload = {"text": cleaned_text or raw_text, "raw": raw_text}
        if actions:
            payload["actions"] = actions
        return payload

    def chat(
        self,
        query: str,
        extra_history: Optional[List[Dict[str, str]]] = None,
        response_format: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Chat with the active model (thread-safe memory & options snapshot)."""
        messages, model_name, options = self._build_request(query, extra_history)
        res = self.client.chat(messages, format=response_format, model=model_name, options=options)
        raw_text = self._extract_raw_text(res)
        payload = self._parse_response(raw_text, response_format)

        with self._lock:
            self.memory.add_user(query)
            self.memory.add_assistant(str(payload.get("text", "")))
        return payload

    def chat_stream(
        self,
        query: str,
        extra_history: Optional[List[Dict[str, str]]] = None,
        response_format: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield incremental delta events and commit finalized response to memory."""
        messages, model_name, options = self._build_request(query, extra_history)
        stream_fn = getattr(self.client, "chat_stream", None)
        if not callable(stream_fn):
            payload = self.chat(query, extra_history=extra_history, response_format=response_format)
            yield {"type": "delta", "delta": str(payload.get("text", "")), "done": True}
            yield {"type": "done", "result": payload}
            return

        collected: List[str] = []
        for chunk in stream_fn(messages, format=response_format, model=model_name, options=options):
            delta = str(chunk.get("delta", "")) if isinstance(chunk, dict) else str(chunk)
            if delta:
                collected.append(delta)
            done = bool(chunk.get("done", False)) if isinstance(chunk, dict) else False
            yield {"type": "delta", "delta": delta, "done": done}

        raw_text = "".join(collected)
        payload = self._parse_response(raw_text, response_format)
        with self._lock:
            self.memory.add_user(query)
            self.memory.add_assistant(str(payload.get("text", "")))
        yield {"type": "done", "result": payload}
