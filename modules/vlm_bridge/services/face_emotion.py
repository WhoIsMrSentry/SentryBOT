"""Lightweight face emotion estimation (VLM-free).

Backends (config-driven):
- ``none`` — always neutral
- ``heuristic`` — brightness/contrast hints
- ``onnx`` — load ``model_path`` when present (FER+ style 8-class head)
- ``remote`` — POST face crop to ``remote_url`` (DeepFace service or ``/vlm/fer/analyze``)
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("vlm_bridge.face_emotion")

_EMOTIONS = (
    "neutral",
    "happiness",
    "surprise",
    "sadness",
    "anger",
    "disgust",
    "fear",
    "contempt",
)

_CANON_MAP = {
    "neutral": "neutral",
    "happiness": "joy",
    "happy": "joy",
    "joy": "joy",
    "surprise": "surprise",
    "sadness": "sadness",
    "sad": "sadness",
    "anger": "anger",
    "angry": "anger",
    "disgust": "disgust",
    "fear": "fear",
    "contempt": "neutral",
}


class FaceEmotionEstimator:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = dict(config or {})
        self.backend = str(cfg.get("backend", "heuristic")).strip().lower()
        self.model_path = str(cfg.get("model_path", "") or "").strip()
        self.min_confidence = float(cfg.get("min_confidence", 0.35))
        self.remote_url = str(cfg.get("remote_url", "") or "").strip()
        self.remote_timeout_s = float(cfg.get("remote_timeout_s", 2.5))
        self.remote_fallback = str(cfg.get("remote_fallback", "heuristic")).strip().lower()
        self._session = None
        self._gateway_base = str(cfg.get("gateway_base_url", "") or "").strip()
        if self.backend == "onnx" and self.model_path:
            self._try_load_onnx()

    def _try_load_onnx(self) -> None:
        path = Path(self.model_path)
        if not path.is_file():
            logger.warning("FER onnx model not found: %s (fallback heuristic)", path)
            self.backend = "heuristic"
            return
        try:
            import onnxruntime as ort  # type: ignore

            self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            logger.info("FER onnx model loaded: %s", path)
        except Exception as exc:
            logger.warning("FER onnx load failed (%s); using heuristic", exc)
            self.backend = "heuristic"
            self._session = None

    @staticmethod
    def _canonical(label: str) -> str:
        key = str(label or "neutral").strip().lower()
        return _CANON_MAP.get(key, "neutral")

    def _encode_face_b64(self, face_roi: Any) -> str:
        import cv2

        ok, buf = cv2.imencode(".jpg", face_roi, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def _resolve_remote_url(self) -> str:
        url = self.remote_url
        if url.startswith("@gateway/"):
            try:
                from modules.gateway.url import gateway_url, resolve_gateway_base_url

                base = self._gateway_base or resolve_gateway_base_url({})
                return gateway_url(base, url.replace("@gateway", "", 1))
            except Exception:
                return ""
        return url

    def _remote_predict(self, face_roi: Any) -> tuple[str, float]:
        url = self._resolve_remote_url()
        if not url:
            return self._fallback_predict(face_roi, self.remote_fallback)
        try:
            import requests

            b64 = self._encode_face_b64(face_roi)
            if not b64:
                return "neutral", 0.0
            resp = requests.post(
                url,
                json={"image_b64": b64},
                timeout=self.remote_timeout_s,
            )
            if resp.status_code != 200:
                return self._fallback_predict(face_roi, self.remote_fallback)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
                data = data["result"]
            label = str(data.get("emotion") or data.get("dominant_emotion") or "neutral")
            conf = float(data.get("confidence", data.get("score", 0.5)) or 0.5)
            return label, conf
        except Exception as exc:
            logger.debug("remote FER failed: %s", exc)
            return self._fallback_predict(face_roi, self.remote_fallback)

    def _fallback_predict(self, face_roi: Any, backend: str) -> tuple[str, float]:
        prev = self.backend
        self.backend = backend
        try:
            if backend == "onnx" and self._session is not None:
                return self._onnx_predict(face_roi)
            return self._heuristic(face_roi)
        finally:
            self.backend = prev

    def _heuristic(self, face_roi: Any) -> tuple[str, float]:
        try:
            import numpy as np

            gray = face_roi
            if hasattr(face_roi, "shape") and len(face_roi.shape) == 3:
                import cv2

                gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            arr = np.asarray(gray, dtype="float32")
            if arr.size == 0:
                return "neutral", 0.0
            mean = float(arr.mean())
            std = float(arr.std())
            if mean < 70:
                return "sadness", 0.42
            if std > 55:
                return "surprise", 0.38
            if mean > 165:
                return "happiness", 0.4
            return "neutral", 0.35
        except Exception:
            return "neutral", 0.0

    def _onnx_predict(self, face_roi: Any) -> tuple[str, float]:
        if self._session is None:
            return self._heuristic(face_roi)
        try:
            import cv2
            import numpy as np

            gray = face_roi
            if len(face_roi.shape) == 3:
                gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (64, 64))
            tensor = resized.astype("float32") / 255.0
            tensor = tensor.reshape(1, 1, 64, 64)
            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: tensor})
            scores = outputs[0].reshape(-1)
            idx = int(scores.argmax())
            conf = float(scores[idx]) if scores.size else 0.0
            label = _EMOTIONS[idx] if 0 <= idx < len(_EMOTIONS) else "neutral"
            return label, conf
        except Exception as exc:
            logger.debug("FER onnx inference failed: %s", exc)
            return self._heuristic(face_roi)

    def estimate(self, face_roi: Any) -> Dict[str, Any]:
        """Return ``{emotion, confidence, backend}`` for a BGR/grayscale face crop."""
        if face_roi is None or self.backend == "none":
            return {"emotion": "neutral", "confidence": 0.0, "backend": self.backend or "none"}

        if self.backend == "remote":
            label, conf = self._remote_predict(face_roi)
            used_backend = "remote"
        elif self.backend == "onnx" and self._session is not None:
            label, conf = self._onnx_predict(face_roi)
            used_backend = "onnx"
        else:
            label, conf = self._heuristic(face_roi)
            used_backend = "heuristic"

        if conf < self.min_confidence:
            label = "neutral"
        return {
            "emotion": self._canonical(label),
            "confidence": round(conf, 3),
            "backend": used_backend,
        }


__all__ = ["FaceEmotionEstimator"]
