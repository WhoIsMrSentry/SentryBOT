from __future__ import annotations
import json
from typing import Dict, List, Optional, Any, Type
import logging
from pydantic import BaseModel
from .clients import OllamaClient
from .memory import ChatMemory
from .tags import extract_llm_tags

logger = logging.getLogger("ollama.chat")


class PersonaProvider:
    def __init__(self, persona_text: str) -> None:
        self.persona_text = persona_text

    def system_prompt(self) -> Dict[str, str]:
        return {"role": "system", "content": self.persona_text}


class OllamaChatService:
    def __init__(self, client: OllamaClient, persona: PersonaProvider, max_history: int = 6) -> None:
        self.client = client
        self.persona = persona
        self.memory = ChatMemory(max_turns=max_history)

    def chat(
        self,
        query: str,
        extra_history: Optional[List[Dict[str, str]]] = None,
        response_format: Optional[Any] = None,
        schema_model: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        messages: List[Dict[str, str]] = [self.persona.system_prompt()]
        if extra_history:
            messages.extend(extra_history)
        messages.extend(self.memory.as_list())
        messages.append({"role": "user", "content": query})
        
        # If schema_model is provided, use its json schema for format
        fmt = response_format
        if schema_model and not fmt:
            fmt = schema_model.model_json_schema()

        res = self.client.chat(messages, format=fmt)
        raw_text = str(res.get("message", {}).get("content", ""))
        
        # Structured Output Handling
        if schema_model:
            try:
                # Validate and parse
                structured_data = schema_model.model_validate_json(raw_text)
                data_dict = structured_data.model_dump()
                
                # Double check mandatory string fields aren't just whitespace/empty
                if not data_dict.get("text", "").strip() or not data_dict.get("thoughts", "").strip():
                    raise ValueError("Model returned empty text or thoughts in structured mode")

                # Update memory with the 'text' field
                text_to_save = data_dict.get("text")
                self.memory.add_user(query)
                self.memory.add_assistant(text_to_save)
                
                payload = {"ok": True, "raw": raw_text, **data_dict}
                return payload
            except Exception as e:
                # Fallback to tag extraction if validation fails or content is empty
                logger.debug(f"Structured validation failed, falling back to tags: {e}")
                pass

        cleaned_text, actions = extract_llm_tags(raw_text)

        self.memory.add_user(query)
        self.memory.add_assistant(cleaned_text)

        payload: Dict[str, Any] = {"text": cleaned_text, "raw": raw_text}
        if actions:
            payload["actions"] = actions
        return payload
