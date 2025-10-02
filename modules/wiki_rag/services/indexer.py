from __future__ import annotations
import os
from typing import Any
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding


def _persona_scoped_dir(base: str, persona: str) -> str:
    return os.path.join(base, persona)


class IndexService:
    def __init__(self, persist_dir: str, knowledge_dir: str, model: str, request_timeout: float = 60.0, persona: str | None = None):
        self.persist_dir = _persona_scoped_dir(persist_dir, persona) if persona else persist_dir
        self.knowledge_dir = _persona_scoped_dir(knowledge_dir, persona) if persona else knowledge_dir
        self.model = model
        self.request_timeout = request_timeout

    def _llm(self) -> Ollama:
        return Ollama(model=self.model, request_timeout=self.request_timeout)

    def build_or_load(self):
        llm = self._llm()
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir, exist_ok=True)
            documents = SimpleDirectoryReader(self.knowledge_dir).load_data()
            index = VectorStoreIndex.from_documents(documents, llm=llm, embed_model=OllamaEmbedding(model_name=self.model))
            index.storage_context.persist(persist_dir=self.persist_dir)
        else:
            storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
            index = load_index_from_storage(storage_context, llm=llm, embed_model=OllamaEmbedding(model_name=self.model))
        return index
