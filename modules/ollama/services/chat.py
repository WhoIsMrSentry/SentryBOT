from __future__ import annotations
from typing import Dict, List, Optional
from .clients import OllamaClient
from .memory import ChatMemory


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

    def chat(self, query: str, extra_history: Optional[List[Dict[str, str]]] = None) -> str:
        messages: List[Dict[str, str]] = [self.persona.system_prompt()]
        if extra_history:
            messages.extend(extra_history)
        messages.extend(self.memory.as_list())
        messages.append({"role": "user", "content": query})
        res = self.client.chat(messages)
        text = str(res.get("message", {}).get("content", ""))
        self.memory.add_user(query)
        self.memory.add_assistant(text)
        return text
