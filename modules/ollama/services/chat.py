from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging
from .clients import LLMClientProtocol
from .memory import ChatMemory

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
        res = self.client.chat(messages, format=response_format, model=model_name, options=options)
        raw_text = str(res.get("message", {}).get("content", ""))
        
        # Native unstructured conversation
        self.memory.add_user(query)
        self.memory.add_assistant(raw_text)

        payload: Dict[str, Any] = {"text": raw_text, "raw": raw_text}
        return payload
