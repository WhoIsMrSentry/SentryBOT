from __future__ import annotations
from typing import Any, Dict, List

import requests

try:
    from ollama import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore


class OllamaClient:
    def __init__(self, base_url: str, model: str, request_timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = request_timeout

        # Prefer the official python client when available, but keep a pure-HTTP
        # fallback so the gateway can call a remote Ollama server without extra deps.
        self._client = Client(host=self.base_url) if Client is not None else None

    def chat(self, messages: List[Dict[str, str]], format: Optional[Any] = None) -> Dict[str, Any]:
        if self._client is not None:
            return self._client.chat(
                model=self.model,
                messages=messages,
                format=format,
                options={"temperature": 0.6},
            )

        # HTTP fallback (Ollama REST API)
        # Ref: POST {base_url}/api/chat
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": format,
            "options": {"temperature": 0.6},
        }
        resp = requests.post(url, json=payload, timeout=float(self.timeout))
        resp.raise_for_status()
        data = resp.json()
        # Normalize shape to match python client expectations used elsewhere.
        if isinstance(data, dict) and "message" in data:
            return data
        # Some proxies/wrappers may respond in OpenAI-ish formats; do best-effort.
        if isinstance(data, dict) and "choices" in data:
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = ""
            return {"message": {"content": content}, "raw": data}
        return {"message": {"content": str(data)}, "raw": data}
