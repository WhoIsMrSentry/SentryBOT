from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging
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
        self.persona_name = persona_name
        self.memory = ChatMemory(max_turns=max_history)
        self.use_persona_as_model = bool(use_persona_as_model)
        self.num_predict = int(num_predict)

    def chat(
        self,
        query: str,
        extra_history: Optional[List[Dict[str, str]]] = None,
        response_format: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Chat with the active model. 
        Identity is baked into the model via Modelfile, so no system prompt injection here.
        """
        messages: List[Dict[str, str]] = []
        if extra_history:
            messages.extend(extra_history)
        messages.extend(self.memory.as_list())
        messages.append({"role": "user", "content": query})
        
        model_name = self.persona_name if self.use_persona_as_model else None
        options: Dict[str, Any] = {"num_predict": self.num_predict}
        raw_text = ""
        if isinstance(res, dict):
            raw_text = str(res.get("message", {}).get("content", ""))
        elif hasattr(res, "message"):
            raw_text = str(getattr(res.message, "content", ""))
        elif hasattr(res, "model_dump"):
            raw_text = str(res.model_dump().get("message", {}).get("content", ""))

        # Fallback action channel: strip [cmd:...] / [[...]] tags the model may
        # emit so the plain-chat path can still drive hardware via apply_actions.
        cleaned_text, actions = extract_llm_tags(raw_text)

        # Native unstructured conversation
        self.memory.add_user(query)
        self.memory.add_assistant(cleaned_text or raw_text)

        payload: Dict[str, Any] = {"text": cleaned_text or raw_text, "raw": raw_text}
        if actions:
            payload["actions"] = actions
        return payload
