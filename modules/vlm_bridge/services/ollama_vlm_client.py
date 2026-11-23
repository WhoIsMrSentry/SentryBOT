"""Remote Ollama VLM client for SentryBOT.

Sends camera frames to a remote Ollama instance running a vision-language
model (e.g. ``qwen3.5:9b``) and parses structured scene observations.

Design constraints:
* RPi5 only does local OpenCV; heavy VLM runs on a remote GPU server.
* We cannot install extra services on the remote â€” only Ollama HTTP API.
* Network traffic must be controlled: frames are resized + JPEG compressed
  before sending, and a minimum interval prevents request flooding.
* At most one in-flight VLM request at a time.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from typing import Any, Dict, Optional

from modules.common.model_roles import DEFAULT_VISION_MODEL
from modules.common.ollama_url import default_ollama_base_url, normalize_ollama_url

logger = logging.getLogger("vlm_bridge.ollama_vlm")

_DEFAULT_BASE_URL = default_ollama_base_url()
_DEFAULT_MODEL = DEFAULT_VISION_MODEL
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_WIDTH = 640
_DEFAULT_JPEG_QUALITY = 70
_DEFAULT_MIN_INTERVAL = 5.0


def _resize_and_encode(
    frame,
    max_width: int = _DEFAULT_MAX_WIDTH,
    jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
) -> str:
    """Resize an OpenCV frame and return a base64-encoded JPEG string."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError("OpenCV (cv2) is required for frame encoding")

    if frame is None or not isinstance(frame, np.ndarray):
        raise ValueError("Invalid frame")

    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        new_w = max_width
        new_h = int(h * scale)
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")

    return base64.b64encode(buf.tobytes()).decode("ascii")


def _parse_vlm_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from VLM output.

    The model may wrap JSON in markdown fences or mix prose with JSON.
    We try several strategies before falling back to a text-only result.
    """
    text = text.strip()
    raw_text = text

    # Strategy 1: direct JSON parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed.setdefault("raw_text", raw_text)
            return parsed
        return {"raw_text": raw_text, "value": parsed}
    except Exception:
        pass

    # Strategy 2: extract from markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            if isinstance(parsed, dict):
                parsed.setdefault("raw_text", raw_text)
                return parsed
            return {"raw_text": raw_text, "value": parsed}
        except Exception:
            pass

    # Strategy 3: find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(0))
            if isinstance(parsed, dict):
                parsed.setdefault("raw_text", raw_text)
                return parsed
            return {"raw_text": raw_text, "value": parsed}
        except Exception:
            pass

    # Strategy 4: regex key-value extraction
    result: Dict[str, Any] = {"raw_text": raw_text}
    for pattern in [
        r'"(\w+)"\s*:\s*"([^"]*)"',
        r'"(\w+)"\s*:\s*(\[[^\]]*\])',
        r'"(\w+)"\s*:\s*(\d+(?:\.\d+)?)',
    ]:
        for m in re.finditer(pattern, text):
            key = m.group(1)
            val = m.group(2)
            try:
                result[key] = json.loads(val)
            except Exception:
                result[key] = val

    return result


# â”€â”€ VLM scene analysis prompt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_SCENE_PROMPT_TR = (
    "Sen bir robotun gÃ¶z sistemisin. KameranÄ±n gÃ¶rdÃ¼ÄŸÃ¼ sahneyi analiz et.\n"
    "JSON formatÄ±nda yanÄ±t ver. Åu alanlarÄ± doldur:\n"
    "{\n"
    '  "summary": "Sahnenin kÄ±sa TÃ¼rkÃ§e Ã¶zeti (2-3 cÃ¼mle)",\n'
    '  "objects": [{"label": "nesne adÄ±", "distance_m": tahmini_mesafe}],\n'
    '  "people": [{"name": "bilinmiyorsa Unknown", "appearance": "kÄ±sa aÃ§Ä±klama", "distance_m": tahmini}],\n'
    '  "hazards": [{"type": "tehlike tÃ¼rÃ¼", "severity": "low|medium|high", "distance_m": tahmini}],\n'
    '  "interesting": ["dikkat Ã§ekici detaylar"],\n'
    '  "recommended_focus": {"type": "person|object|hazard", "reason": "neden odaklanmalÄ±"}\n'
    "}\n"
    "Sadece JSON dÃ¶ndÃ¼r, baÅŸka aÃ§Ä±klama ekleme. TÃ¼rkÃ§e yaz."
)

_QUESTION_PROMPT_TR = (
    "Sen bir robotun gÃ¶z sistemisin. KameranÄ±n gÃ¶rdÃ¼ÄŸÃ¼ sahneyi analiz et "
    "ve ÅŸu soruyu yanÄ±tla:\n\n"
    "Soru: {question}\n\n"
    "TÃ¼rkÃ§e, doÄŸal ve kÄ±sa yanÄ±t ver. GÃ¶rmediÄŸin ÅŸeyi tahmin etme, "
    "\"gÃ¶remiyorum\" de."
)


class OllamaVLMClient:
    """HTTP client for remote Ollama VLM inference.

    Thread-safe; enforces at most one in-flight request.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.base_url = normalize_ollama_url(cfg.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")
        self.model = str(cfg.get("model", _DEFAULT_MODEL))
        self.timeout = float(cfg.get("timeout_s", _DEFAULT_TIMEOUT))
        self.max_image_width = int(cfg.get("max_image_width", _DEFAULT_MAX_WIDTH))
        self.jpeg_quality = int(cfg.get("jpeg_quality", _DEFAULT_JPEG_QUALITY))
        self.min_interval_s = float(cfg.get("min_interval_s", _DEFAULT_MIN_INTERVAL))
        self.num_predict = int(cfg.get("num_predict", 256))
        self.num_ctx = int(cfg.get("num_ctx", 8192))
        raw_ka = cfg.get("keep_alive", -1)
        self.keep_alive: Any = raw_ka if raw_ka is not None else -1

        self._lock = threading.Lock()
        self._in_flight = False
        self._last_call: float = 0.0
        self._call_count: int = 0
        self._error_count: int = 0
        self._session = None

    def _http_session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def analyze_frame(
        self,
        frame,
        *,
        custom_prompt: str = "",
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Send a frame to the remote VLM for scene analysis.

        Args:
            frame: OpenCV numpy array (BGR).
            custom_prompt: Override the default scene analysis prompt.
            force: Bypass minimum interval check.

        Returns:
            Parsed JSON dict, or None if rate-limited / error.
        """
        now = time.time()

        with self._lock:
            if self._in_flight:
                logger.debug("VLM call skipped: request already in flight")
                return None
            if not force and (now - self._last_call) < self.min_interval_s:
                logger.debug("VLM call skipped: rate limit (%.1fs remaining)",
                             self.min_interval_s - (now - self._last_call))
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
            result = self._call_ollama(prompt, image_b64)
            latency = (time.time() - start) * 1000
            if result:
                result["_latency_ms"] = round(latency, 1)
                self._call_count += 1
                logger.info("VLM analysis completed in %.0fms", latency)
            return result
        except Exception as exc:
            self._error_count += 1
            logger.warning("VLM analysis failed: %s", exc)
            return None
        finally:
            with self._lock:
                self._in_flight = False

    def ask_about_scene(
        self,
        frame,
        question: str,
        force: bool = True,
        *,
        context_hints: Optional[str] = None,
    ) -> Optional[str]:
        """Ask a specific question about what the camera sees.

        Returns natural language answer string.
        """
        prompt = _QUESTION_PROMPT_TR.format(question=question)
        hints = str(context_hints or "").strip()
        if hints:
            prompt = (
                f"{prompt}\n\n"
                f"Yerel tanıma ipuçları (görüntüyle uyuşuyorsa kimlik/nesne adlandırmada kullan): {hints}"
            )
        result = self.analyze_frame(frame, custom_prompt=prompt, force=force)
        if result is None:
            return None
        # For question mode, we expect raw text not JSON
        return result.get("raw_text") or result.get("summary") or str(result)

    def extract_text_ocr(
        self,
        frame,
        *,
        languages: Optional[list[str]] = None,
        force: bool = True,
    ) -> Optional[str]:
        """Extract visible printed or on-screen text from a frame using Ollama VLM."""
        lang_hint = f" Odak dilleri: {', '.join(languages)}." if languages else ""
        prompt = (
            "Görüntüdeki veya ekrandaki tüm okunabilir yazıları, başlıkları, kişi isimlerini "
            "ve etiketleri olduğu gibi satır satır çıkar. Yalnızca gördüğün metni yaz; "
            f"hiç metin yoksa sadece YOK yaz.{lang_hint}"
        )
        result = self.analyze_frame(frame, custom_prompt=prompt, force=force)
        if result is None:
            return None
        raw = str(result.get("raw_text") or result.get("summary") or "").strip()
        if not raw or raw.upper() == "YOK":
            return None
        return raw

    def is_available(self) -> bool:
        """Quick health check against the remote Ollama server."""
        try:
            resp = self._http_session().get(f"{self.base_url}/api/tags", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "in_flight": self._in_flight,
            "last_call_age_s": round(time.time() - self._last_call, 1) if self._last_call else None,
        }

    # â”€â”€ Internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _call_ollama(self, prompt: str, image_b64: str) -> Optional[Dict[str, Any]]:
        """Make the actual HTTP request to Ollama /api/chat."""
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.3,
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
            },
        }

        resp = self._http_session().post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text content
        content = ""
        if isinstance(data, dict):
            msg = data.get("message", {})
            if isinstance(msg, dict):
                content = str(msg.get("content", ""))
            elif isinstance(data.get("response"), str):
                content = data["response"]

        if not content:
            return None

        return _parse_vlm_json(content)


__all__ = ["OllamaVLMClient"]
