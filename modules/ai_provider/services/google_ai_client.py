from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ollama.google_ai_client")


class GoogleAIStudioClient:
    """Disabled Google AI Studio compatibility client.

    SentryBOT is configured for local-only Ollama routing.
    This class exists only so legacy imports keep compiling.
    """

    _RATE_LIMIT_COOLDOWN_S: float = 0.0

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen3.5:9b",
        base_url: str = "http://whoismrsentry.local:11434",
        request_timeout: float = 60.0,
    ) -> None:
        self.api_key = ""
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = request_timeout

    @classmethod
    def is_rate_limited(cls, api_key: str = "") -> bool:
        return False

    @classmethod
    def rate_limit_remaining_s(cls, api_key: str = "") -> int:
        return 0

    def _is_rate_limited(self) -> bool:
        return False

    def create_model(self, name: str, modelfile: str) -> bool:
        logger.warning("Google provider is disabled; use local Ollama.")
        return False

    def pull_model(self, name: str) -> bool:
        logger.warning("Google provider is disabled; use local Ollama.")
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
        raise RuntimeError("Google provider is disabled. Use local Ollama provider.")

    def generate_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        mime_type: str = "image/jpeg",
        model: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise RuntimeError("Google VLM provider is disabled. Use local Ollama provider.")
