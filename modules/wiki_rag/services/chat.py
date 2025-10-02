from __future__ import annotations
from typing import Any
from llama_index.core import Settings
from llama_index.core.memory import ChatMemoryBuffer


class ChatEngineFactory:
    def __init__(self, index, llm, persona_text: str, memory_tokens: int = 1500) -> None:
        self.index = index
        self.llm = llm
        self.persona_text = persona_text
        self.memory_tokens = memory_tokens

    def build(self):
        memory = ChatMemoryBuffer.from_defaults(token_limit=self.memory_tokens, llm=self.llm)
        chat_engine = self.index.as_chat_engine(
            chat_mode="context",
            llm=self.llm,
            memory=memory,
            system_prompt=self.persona_text,
        )
        return chat_engine
