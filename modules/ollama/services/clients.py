from __future__ import annotations
import logging
import os
from typing import Any, Dict, List, Optional, Protocol, Tuple

import requests

try:
    from ollama import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore


logger = logging.getLogger("ollama.clients")


class OllamaClient:
    def __init__(self, base_url: str, model: str, request_timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = request_timeout

        # Prefer the official python client when available, but keep a pure-HTTP
        # fallback so the gateway can call a remote Ollama server without extra deps.
        self._client = Client(host=self.base_url) if Client is not None else None

    def create_model(self, name: str, modelfile: str) -> bool:
        """Create a new model from a Modelfile string."""
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
        """Pull model weights from registry into the target Ollama host."""
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
        """List model names available on the target Ollama host."""
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

        if self._client is not None:
            return self._client.chat(
                model=selected_model,
                messages=messages,
                format=format,
                options=merged_options,
            )

        # HTTP fallback (Ollama REST API)
        # Ref: POST {base_url}/api/chat
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "stream": False,
            "format": format,
            "options": merged_options,
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


class GoogleAIStudioClient:
    """Google AI Studio (Gemini) REST istemcisi."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com",
        request_timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = request_timeout

    @staticmethod
    def _to_gemini_parts(messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        system_chunks: List[str] = []
        contents: List[Dict[str, Any]] = []

        for m in messages:
            role = str(m.get("role", "user"))
            text = str(m.get("content", ""))
            if not text.strip():
                continue

            if role == "system":
                system_chunks.append(text)
                continue

            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        system_instruction = "\n\n".join(system_chunks).strip() or None
        return system_instruction, contents

    def create_model(self, name: str, modelfile: str) -> bool:
        """Gemini doesn't support local Modelfile creation; skip or mock."""
        logger.warning("create_model is not supported on Google AI Studio.")
        return False

    def pull_model(self, name: str) -> bool:
        logger.warning("pull_model is not supported on Google AI Studio.")
        return False

    def list_models(self) -> List[str]:
        return []

    def chat(
        self,
        messages: List[Dict[str, str]],
        format: Optional[Any] = None,
        *,
        options: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_model = model or self.model
        system_instruction, contents = self._to_gemini_parts(messages)

        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        generation_config: Dict[str, Any] = {"temperature": 0.6}
        if isinstance(options, dict):
            if "temperature" in options:
                generation_config["temperature"] = options["temperature"]

        if isinstance(format, dict):
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = format

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{self.base_url}/v1beta/models/{selected_model}:generateContent"
        resp = requests.post(
            url,
            params={"key": self.api_key},
            json=payload,
            timeout=float(self.timeout),
        )
        resp.raise_for_status()
        data = resp.json()

        text = ""
        try:
            parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
            text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
        except Exception:
            text = ""

        return {"message": {"content": text}, "raw": data}


def create_llm_client(cfg: Dict[str, Any]) -> Tuple[LLMClientProtocol, str]:
    llm_cfg = cfg.get("llm", {}) or {}
    provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"

    if provider in {"google", "google_ai_studio", "gemini"}:
        gcfg = cfg.get("google_ai_studio", {}) or {}
        api_key = str(gcfg.get("api_key", "")).strip() or str(os.environ.get("GOOGLE_API_KEY", "")).strip()
        model = str(gcfg.get("model", "gemini-1.5-flash")).strip() or "gemini-1.5-flash"
        base_url = str(gcfg.get("base_url", "https://generativelanguage.googleapis.com")).strip()
        timeout = float(gcfg.get("request_timeout", 60.0))
        if not api_key:
            raise RuntimeError("Google AI Studio selected but api_key is missing")
        return GoogleAIStudioClient(api_key=api_key, model=model, base_url=base_url, request_timeout=timeout), "google_ai_studio"

    ocfg = cfg.get("ollama", {}) or {}
    base_url = str(ocfg.get("base_url", "http://localhost:11435"))
    model = str(ocfg.get("model", "llama3.2:3b"))
    timeout = float(ocfg.get("request_timeout", 60.0))
    return OllamaClient(base_url=base_url, model=model, request_timeout=timeout), "ollama"
