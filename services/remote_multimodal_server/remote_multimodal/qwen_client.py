from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

import cv2
import requests

from .config import RuntimeConfig

logger = logging.getLogger("remote_multimodal.qwen_client")


class QwenVlmClient:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.enabled = bool(cfg.enable_qwen_vlm)
        self.endpoint = str(cfg.qwen_endpoint or "").strip()
        self.primary_model = str(cfg.qwen_primary_model or "").strip()
        self.fallback_model = str(cfg.qwen_fallback_model or "").strip()
        self.timeout_s = float(cfg.qwen_timeout_s)
        self.num_predict = int(cfg.qwen_num_predict)
        self.num_ctx = int(cfg.qwen_num_ctx)
        self.temperature = float(cfg.qwen_temperature)
        self._session = requests.Session()

    def analyze_frame(self, frame: Any) -> Dict[str, Any]:
        if not self.enabled or not self.endpoint or not self.primary_model:
            return {"ok": False, "error": "qwen disabled"}
        image_b64 = self._encode_frame(frame)
        for model in self._models():
            result = self._call_model(model=model, image_b64=image_b64)
            if result.get("ok"):
                return result
        return {"ok": False, "error": "qwen request failed"}

    def _models(self) -> List[str]:
        models = [self.primary_model]
        if self.fallback_model and self.fallback_model != self.primary_model:
            models.append(self.fallback_model)
        return models

    @staticmethod
    def _encode_frame(frame: Any) -> str:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        if not ok:
            raise ValueError("frame encode failed")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def _call_model(self, model: str, image_b64: str) -> Dict[str, Any]:
        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a robot vision co-processor. Return strict compact JSON with keys: "
                        "summary, persona_interpretation, hazards, suggested_focus, confidence. "
                        "hazards must be an array of short strings."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Analyze the scene for human-robot interaction. "
                        "Focus on safety, people intent, and immediate actions."
                    ),
                    "images": [image_b64],
                },
            ],
        }
        try:
            resp = self._session.post(self.endpoint, json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            body = resp.json()
            content = str(((body.get("message") or {}).get("content")) or "").strip()
            parsed = self._parse_json_text(content)
            if not parsed:
                return {"ok": False, "error": "qwen invalid json", "model": model}
            return {
                "ok": True,
                "model": model,
                "summary": str(parsed.get("summary", "")).strip(),
                "persona_interpretation": str(parsed.get("persona_interpretation", "")).strip(),
                "hazards": parsed.get("hazards", []),
                "suggested_focus": str(parsed.get("suggested_focus", "")).strip(),
                "confidence": float(parsed.get("confidence", 0.0) or 0.0),
            }
        except Exception as exc:
            logger.debug("Qwen call failed for %s: %s", model, exc)
            return {"ok": False, "error": "qwen request error", "model": model}

    @staticmethod
    def _parse_json_text(content: str) -> Optional[Dict[str, Any]]:
        text = content.strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None
