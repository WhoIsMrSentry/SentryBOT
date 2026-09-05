"""Google AI Studio (Gemini) vision client for scene analysis."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("vlm_bridge.google_vlm")

try:
    from .ollama_vlm_client import (
        _QUESTION_PROMPT_TR,
        _SCENE_PROMPT_TR,
        _parse_vlm_json,
        _resize_and_encode,
    )
except Exception:
    from modules.vlm_bridge.services.ollama_vlm_client import (  # type: ignore
        _QUESTION_PROMPT_TR,
        _SCENE_PROMPT_TR,
        _parse_vlm_json,
        _resize_and_encode,
    )


class GoogleVLMClient:
    """Gemini multimodal client with the same surface as :class:`OllamaVLMClient`."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        from modules.ai_provider.services.clients import GoogleAIStudioClient, _sanitize_google_api_key

        cfg = config or {}
        google_cfg = cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio"), dict) else cfg

        api_key = _sanitize_google_api_key(google_cfg.get("api_key", ""))
        if not api_key:
            import os

            api_key = _sanitize_google_api_key(os.environ.get("GOOGLE_API_KEY", ""))
        if not api_key:
            raise RuntimeError("Google AI Studio vision selected but api_key is missing")

        from modules.system_control.config_center.gemini_model import DEFAULT_GEMINI_MODEL

        model = str(google_cfg.get("model", cfg.get("model", DEFAULT_GEMINI_MODEL))).strip() or DEFAULT_GEMINI_MODEL
        base_url = str(
            google_cfg.get("base_url", "https://generativelanguage.googleapis.com")
        ).strip()
        timeout = float(google_cfg.get("request_timeout", cfg.get("timeout_s", 45.0)))

        self._client = GoogleAIStudioClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            request_timeout=timeout,
        )
        self.model = model
        self.timeout = timeout
        self.max_image_width = int(cfg.get("max_image_width", 640))
        self.jpeg_quality = int(cfg.get("jpeg_quality", 70))
        self.min_interval_s = float(cfg.get("min_interval_s", 5.0))
        self.num_predict = int(cfg.get("num_predict", 256))

        self._lock = threading.Lock()
        self._in_flight = False
        self._last_call: float = 0.0
        self._call_count = 0
        self._error_count = 0

    def analyze_frame(
        self,
        frame,
        *,
        custom_prompt: str = "",
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            if self._in_flight:
                return None
            if not force and (now - self._last_call) < self.min_interval_s:
                return None
            self._in_flight = True
            self._last_call = now

        try:
            image_b64 = _resize_and_encode(
                frame,
                max_width=self.max_image_width,
                jpeg_quality=self.jpeg_quality,
            )
        except Exception as exc:
            logger.warning("Frame encoding failed: %s", exc)
            with self._lock:
                self._in_flight = False
            return None

        prompt = custom_prompt or _SCENE_PROMPT_TR
        start = time.time()
        try:
            text = self._client.generate_with_image(
                prompt,
                image_b64,
                options={"temperature": 0.3},
            )
            if not text:
                return None
            result = _parse_vlm_json(text)
            result["_latency_ms"] = round((time.time() - start) * 1000, 1)
            self._call_count += 1
            return result
        except Exception as exc:
            self._error_count += 1
            logger.warning("Gemini VLM analysis failed: %s", exc)
            return None
        finally:
            with self._lock:
                self._in_flight = False

    def ask_about_scene(self, frame, question: str, force: bool = True) -> Optional[str]:
        prompt = _QUESTION_PROMPT_TR.format(question=question)
        result = self.analyze_frame(frame, custom_prompt=prompt, force=force)
        if result is None:
            return None
        return result.get("raw_text") or result.get("summary") or str(result)

    def is_available(self) -> bool:
        return bool(getattr(self._client, "api_key", ""))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider": "google_ai_studio",
            "model": self.model,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "in_flight": self._in_flight,
            "last_call_age_s": round(time.time() - self._last_call, 1) if self._last_call else None,
        }


def create_vision_llm_client(config: Dict[str, Any]):
    """Factory: returns OllamaVLMClient or GoogleVLMClient based on provider."""
    vlm_cfg = config.get("vision_llm", {}) if isinstance(config.get("vision_llm"), dict) else {}
    provider = str(vlm_cfg.get("provider", "ollama")).strip().lower() or "ollama"

    if provider in {"google", "google_ai_studio", "gemini"}:
        merged = dict(vlm_cfg)
        if isinstance(config.get("google_ai_studio"), dict):
            merged["google_ai_studio"] = config["google_ai_studio"]
        return GoogleVLMClient(merged)

    try:
        from .ollama_vlm_client import OllamaVLMClient
    except Exception:
        from modules.vlm_bridge.services.ollama_vlm_client import OllamaVLMClient  # type: ignore

    return OllamaVLMClient(vlm_cfg)


__all__ = ["GoogleVLMClient", "create_vision_llm_client"]
