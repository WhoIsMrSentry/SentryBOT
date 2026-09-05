from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Protocol, Tuple

import requests

try:
    from ollama import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore

from .google_ai_client import GoogleAIStudioClient
from modules.common.ollama_url import normalize_ollama_url  # noqa: E402

logger = logging.getLogger("ollama.clients")

_GOOGLE_API_KEY_PLACEHOLDERS = {
    "your-google-api-key",
    "your_google_api_key",
    "your-api-key",
    "changeme",
    "replace_me",
    "replace-with-your-key",
}


def _sanitize_google_api_key(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in _GOOGLE_API_KEY_PLACEHOLDERS:
        return ""
    if "your-google-api-key" in lowered:
        return ""
    return value


def _normalize_ollama_daemon_base_url(raw: Any) -> str:
    value = str(raw or "").strip().rstrip("/")
    lowered = value.lower()
    if (
        not value
        or "@gateway" in lowered
        or lowered in {"http://127.0.0.1:8080", "http://localhost:8080"}
        or lowered.startswith("http://127.0.0.1:8080/")
        or lowered.startswith("http://localhost:8080/")
        or lowered.endswith("/ollama")
        or lowered.endswith("/ollama/chat")
    ):
        return "http:"
    return value


_INFERENCE_SEMAPHORE = threading.BoundedSemaphore(1)


class OllamaClient:
    def __init__(self, base_url: str, model: str, request_timeout: float = 60.0) -> None:
        self.base_url = normalize_ollama_url(base_url)
        self.model = model
        self.timeout = request_timeout
        self._client = Client(host=self.base_url) if Client is not None else None

    def create_model(self, name: str, modelfile: str) -> bool:
        url = f"{self.base_url}/api/create"
        payload = {
            "name": name,
            "modelfile": modelfile,
            "stream": False
        }
        try:
            resp = requests.post(url, json=payload, timeout=float(self.timeout * 2))
            resp.raise_for_status()
            logger.info(f"Ollama model '{name}' created/updated successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to create Ollama model '{name}': {e}")
            return False

    def pull_model(self, name: str) -> bool:
        model_name = str(name or "").strip()
        if not model_name:
            return False

        url = f"{self.base_url}/api/pull"
        payload = {"name": model_name, "stream": False}
        try:
            resp = requests.post(url, json=payload, timeout=float(self.timeout * 4))
            resp.raise_for_status()
            logger.info("Ollama model '%s' pulled successfully.", model_name)
            return True
        except Exception as e:
            logger.error("Failed to pull Ollama model '%s': %s", model_name, e)
            return False

    def list_models(self) -> List[str]:
        url = f"{self.base_url}/api/tags"
        try:
            resp = requests.get(url, timeout=float(self.timeout))
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.error("Failed to list Ollama models: %s", e)
            return []

        items = data.get("models", []) if isinstance(data, dict) else []
        names: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
        return names

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_model = model or self.model
        merged_options: Dict[str, Any] = {"temperature": 0.6}
        if isinstance(options, dict):
            merged_options.update(options)

        with _INFERENCE_SEMAPHORE:
            if self._client is not None:
                try:
                    resp = self._client.chat(
                        model=selected_model,
                        messages=messages,
                        format=format,
                        options=merged_options,
                    )
                except Exception:
                    resp = None
                if resp is not None:
                    if isinstance(resp, dict):
                        return resp
                    if hasattr(resp, "model_dump"):
                        return resp.model_dump()
                    if hasattr(resp, "dict"):
                        return resp.dict()
                    msg = getattr(resp, "message", None)
                    content = getattr(msg, "content", "") if msg else ""
                    return {"message": {"content": str(content)}, "raw": str(resp)}

            url = f"{self.base_url}/api/chat"
            payload: Dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": format,
                "options": merged_options,
            }
            resp = requests.post(url, json=payload, timeout=float(self.timeout))
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "message" in data:
                return data
            if isinstance(data, dict) and "choices" in data:
                try:
                    content = data["choices"][0]["message"]["content"]
                except Exception:
                    content = ""
                return {"message": {"content": content}, "raw": data}
            return {"message": {"content": str(data)}, "raw": data}


class LLMClientProtocol(Protocol):
    model: str

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    def create_model(self, name: str, modelfile: str) -> bool:
        ...

    def pull_model(self, name: str) -> bool:
        ...

    def list_models(self) -> List[str]:
        ...


def create_llm_client(cfg: Dict[str, Any]) -> Tuple[LLMClientProtocol, str]:
    from modules.system_control.config_center.gemini_model import DEFAULT_GEMINI_MODEL
    llm_cfg = cfg.get("llm", {}) or {}
    provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"

    if provider in {"google", "google_ai_studio", "gemini"}:
        gcfg = cfg.get("google_ai_studio", {}) or {}
        api_key = _sanitize_google_api_key(gcfg.get("api_key", ""))
        if not api_key:
            api_key = _sanitize_google_api_key(os.environ.get("GOOGLE_API_KEY", ""))
        model = str(gcfg.get("model", DEFAULT_GEMINI_MODEL)).strip() or DEFAULT_GEMINI_MODEL
        base_url = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com")).strip()
        timeout = float(gcfg.get("request_timeout", 60.0))
        if not api_key:
            raise RuntimeError("Google AI Studio selected but api_key is missing")
        return GoogleAIStudioClient(api_key=api_key, model=model, base_url=base_url, request_timeout=timeout), "google_ai_studio"

    ocfg = cfg.get("ollama", {}) or {}
    base_url = str(ocfg.get("base_url", "http:"))
    model = str(ocfg.get("model", "llama3.2:3b"))
    timeout = float(ocfg.get("request_timeout", 60.0))
    return OllamaClient(base_url=base_url, model=model, request_timeout=timeout), "ollama"

