from __future__ import annotations
import logging
import os
import time
from typing import Any, Dict, List, Optional, Protocol, Tuple

import requests

from modules.config_center.gemini_model import DEFAULT_GEMINI_MODEL
from modules.config_center.log_redact import redact_secrets

try:
    from ollama import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None  # type: ignore


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

    _rate_limited_until_by_key: Dict[str, float] = {}
    _RATE_LIMIT_COOLDOWN_S: float = 90.0

    @staticmethod
    def _rate_bucket(api_key: str) -> str:
        key = str(api_key or "").strip()
        return key[-8:] if len(key) >= 8 else key or "default"

    @classmethod
    def is_rate_limited(cls, api_key: str = "") -> bool:
        if api_key:
            return time.time() < cls._rate_limited_until_by_key.get(cls._rate_bucket(api_key), 0.0)
        return any(time.time() < t for t in cls._rate_limited_until_by_key.values())

    @classmethod
    def rate_limit_remaining_s(cls, api_key: str = "") -> int:
        if api_key:
            until = cls._rate_limited_until_by_key.get(cls._rate_bucket(api_key), 0.0)
            return max(0, int(until - time.time()))
        if not cls._rate_limited_until_by_key:
            return 0
        latest = max(cls._rate_limited_until_by_key.values())
        return max(0, int(latest - time.time()))

    def _is_rate_limited(self) -> bool:
        return self.is_rate_limited(self.api_key)

    def _arm_rate_limit(self) -> None:
        self._rate_limited_until_by_key[self._rate_bucket(self.api_key)] = (
            time.time() + self._RATE_LIMIT_COOLDOWN_S
        )

    @staticmethod
    def _parse_api_error(resp: requests.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict):
                err = body.get("error", {})
                if isinstance(err, dict):
                    return redact_secrets(str(err.get("message", resp.text[:300])))
        except Exception:
            pass
        return redact_secrets(resp.text[:300])

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
        selected_model = str(model or self.model).strip() or self.model
        # Guard against accidental persona-name override (e.g. "sentry").
        if model and not selected_model.lower().startswith("gemini"):
            logger.warning(
                "Ignoring non-Gemini model override for Google provider: %s",
                selected_model,
            )
            selected_model = self.model
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
        data = self._post_generate_content(url, payload)
        text = ""
        try:
            parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
            text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
        except Exception:
            text = ""

        return {"message": {"content": text}, "raw": data}

    def _post_generate_content(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._is_rate_limited():
            raise RuntimeError(
                f"Gemini rate limited; retry in {self.rate_limit_remaining_s(self.api_key)}s"
            )
        backoff_s = (2.0, 5.0)
        last_exc: Optional[Exception] = None
        for attempt in range(len(backoff_s) + 1):
            try:
                resp = requests.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=float(self.timeout),
                )
                if resp.status_code == 429:
                    if attempt < len(backoff_s):
                        logger.warning(
                            "Gemini rate limited (429); retrying in %.0fs (attempt %d/%d)",
                            backoff_s[attempt],
                            attempt + 1,
                            len(backoff_s),
                        )
                        time.sleep(backoff_s[attempt])
                        continue
                    self._arm_rate_limit()
                    raise RuntimeError(
                        f"Gemini rate limited (429); cooldown {int(self._RATE_LIMIT_COOLDOWN_S)}s"
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Gemini API {resp.status_code}: {self._parse_api_error(resp)}"
                    )
                return resp.json()
            except requests.HTTPError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt < len(backoff_s):
                        time.sleep(backoff_s[attempt])
                        continue
                    self._arm_rate_limit()
                    raise RuntimeError(
                        f"Gemini rate limited (429); cooldown {int(self._RATE_LIMIT_COOLDOWN_S)}s"
                    ) from exc
                if exc.response is not None:
                    raise RuntimeError(
                        f"Gemini API {exc.response.status_code}: "
                        f"{self._parse_api_error(exc.response)}"
                    ) from exc
                raise RuntimeError(redact_secrets(str(exc))) from exc
            except Exception as exc:
                last_exc = exc
                raise
        if last_exc:
            raise RuntimeError(redact_secrets(str(last_exc))) from last_exc
        raise RuntimeError("Gemini request failed")

    def generate_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        mime_type: str = "image/jpeg",
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Multimodal generateContent (text + inline image)."""
        selected_model = str(model or self.model).strip() or self.model
        if model and not selected_model.lower().startswith("gemini"):
            selected_model = self.model

        generation_config: Dict[str, Any] = {"temperature": 0.3}
        if isinstance(options, dict) and "temperature" in options:
            generation_config["temperature"] = options["temperature"]

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": str(prompt or "")},
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                    ],
                }
            ],
            "generationConfig": generation_config,
        }

        url = f"{self.base_url}/v1beta/models/{selected_model}:generateContent"
        data = self._post_generate_content(url, payload)
        try:
            parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
            return "\n".join(
                str(p.get("text", "")) for p in parts if isinstance(p, dict)
            ).strip()
        except Exception:
            return ""


def create_llm_client(cfg: Dict[str, Any]) -> Tuple[LLMClientProtocol, str]:
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
    base_url = str(ocfg.get("base_url", "http://127.0.0.1:11434"))
    model = str(ocfg.get("model", "llama3.2:3b"))
    timeout = float(ocfg.get("request_timeout", 60.0))
    return OllamaClient(base_url=base_url, model=model, request_timeout=timeout), "ollama"
