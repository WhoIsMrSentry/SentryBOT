from __future__ import annotations
from typing import Any, Dict, List

try:
    from ollama import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore


class OllamaClient:
    def __init__(self, base_url: str, model: str, request_timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = request_timeout
        if Client is None:
            raise RuntimeError("ollama package is not installed")
        self._client = Client(host=self.base_url)

    def chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return self._client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": 0.6},
        )
