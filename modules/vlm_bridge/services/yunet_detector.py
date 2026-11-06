"""YuNet Face Detector & SFace Feature Extractor for SentryBOT.

Provides ultra-fast (<15ms on CPU) deep-learning based face detection
(OpenCV FaceDetectorYN) and face recognition embeddings (OpenCV FaceRecognizerSF)
with graceful fallback when OpenCV DNN or model weights are missing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

logger = logging.getLogger("vlm_bridge.yunet")

_YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
_SFACE_MODEL_NAME = "face_recognition_sface_2021dec.onnx"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _find_model_file(filename: str) -> Optional[str]:
    candidates = [
        _repo_root() / "models" / "face_models" / filename,
        _repo_root() / "models" / "yunet" / filename,
        _repo_root() / "models" / filename,
        Path("models") / "face_models" / filename,
        Path("models") / filename,
    ]
    for c in candidates:
        if c.is_file():
            return str(c.resolve())
    return None


class YuNetDetector:
    """OpenCV FaceDetectorYN wrapper for fast, landmark-aware face detection."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        self.model_path = model_path or _find_model_file(_YUNET_MODEL_NAME)
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.top_k = int(top_k)
        self._detector: Any = None
        self._current_size: Tuple[int, int] = (0, 0)
        self._init_detector()

    def _init_detector(self) -> None:
        if cv2 is None or not hasattr(cv2, "FaceDetectorYN"):
            logger.info("cv2.FaceDetectorYN is not supported in this OpenCV build")
            return
        if not self.model_path or not os.path.isfile(self.model_path):
            logger.info("YuNet model file not found (%s)", self.model_path)
            return
        try:
            self._detector = cv2.FaceDetectorYN.create(
                self.model_path,
                "",
                (320, 320),
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                top_k=self.top_k,
            )
            self._current_size = (320, 320)
            logger.info("YuNet face detector initialized from %s", self.model_path)
        except Exception as exc:
            logger.warning("Failed to create cv2.FaceDetectorYN: %s", exc)
            self._detector = None

    @property
    def is_available(self) -> bool:
        return self._detector is not None

    def detect(
        self,
        image: np.ndarray,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Detect faces in image.

        Returns a list of dicts:
            {
                "bbox": [x1, y1, x2, y2],
                "confidence": float,
                "landmarks": [(x, y), ...], # 5 landmarks: right_eye, left_eye, nose, right_mouth, left_mouth
                "raw_face": np.ndarray,      # 15-float row for SFace
            }
        """
        if not self.is_available or image is None or not hasattr(image, "shape"):
            return []
        h, w = image.shape[:2]
        if h <= 0 or w <= 0:
            return []

        try:
            if (w, h) != self._current_size:
                self._detector.setInputSize((w, h))
                self._current_size = (w, h)
            if score_threshold is not None and score_threshold != self.score_threshold:
                self._detector.setScoreThreshold(float(score_threshold))

            retval, faces = self._detector.detect(image)
        except Exception as exc:
            logger.debug("YuNet detect call failed: %s", exc)
            return []

        if not retval or faces is None or len(faces) == 0:
            return []

        out: List[Dict[str, Any]] = []
        for face in faces:
            try:
                x, y, bw, bh = face[0:4]
                conf = float(face[14])
                x1 = max(0, min(w - 1, int(x)))
                y1 = max(0, min(h - 1, int(y)))
                x2 = max(0, min(w, int(x + bw)))
                y2 = max(0, min(h, int(y + bh)))
                if x2 <= x1 or y2 <= y1:
                    continue

                landmarks = []
                for i in range(4, 14, 2):
                    landmarks.append((float(face[i]), float(face[i + 1])))

                out.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(conf, 4),
                    "landmarks": landmarks,
                    "raw_face": face.copy(),
                })
            except Exception:
                continue

        return out


class SFaceRecognizer:
    """OpenCV FaceRecognizerSF wrapper for 128D face feature extraction and matching."""

    # Standard SFace cosine threshold: >= 0.363 indicates the same identity
    COSINE_MATCH_THRESHOLD = 0.363

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.model_path = model_path or _find_model_file(_SFACE_MODEL_NAME)
        self._recognizer: Any = None
        self._init_recognizer()

    def _init_recognizer(self) -> None:
        if cv2 is None or not hasattr(cv2, "FaceRecognizerSF"):
            logger.info("cv2.FaceRecognizerSF is not supported in this OpenCV build")
            return
        if not self.model_path or not os.path.isfile(self.model_path):
            logger.info("SFace model file not found (%s)", self.model_path)
            return
        try:
            self._recognizer = cv2.FaceRecognizerSF.create(self.model_path, "")
            logger.info("SFace face recognizer initialized from %s", self.model_path)
        except Exception as exc:
            logger.warning("Failed to create cv2.FaceRecognizerSF: %s", exc)
            self._recognizer = None

    @property
    def is_available(self) -> bool:
        return self._recognizer is not None

    def extract_feature(self, image: np.ndarray, raw_face: np.ndarray) -> Optional[np.ndarray]:
        """Align crop and extract 128-dimensional dense feature vector."""
        if not self.is_available or image is None or raw_face is None:
            return None
        try:
            aligned = self._recognizer.alignCrop(image, raw_face)
            feat = self._recognizer.feature(aligned)
            if feat is not None and hasattr(feat, "shape") and feat.size == 128:
                vec = feat.flatten().astype(np.float32)
                norm = np.linalg.norm(vec)
                return vec / norm if norm > 0 else vec
            return None
        except Exception as exc:
            logger.debug("SFace feature extraction failed: %s", exc)
            return None

    def match(self, feature1: np.ndarray, feature2: np.ndarray) -> float:
        """Compute cosine similarity score between two 128D feature vectors."""
        if feature1 is None or feature2 is None:
            return -1.0
        try:
            f1 = np.asarray(feature1, dtype=np.float32).reshape(1, -1)
            f2 = np.asarray(feature2, dtype=np.float32).reshape(1, -1)
            if self._recognizer is not None:
                score = self._recognizer.match(f1, f2, cv2.FaceRecognizerSF_FR_COSINE)
                return float(score)
            n1 = np.linalg.norm(f1)
            n2 = np.linalg.norm(f2)
            if n1 <= 0 or n2 <= 0:
                return -1.0
            return float(np.dot(f1, f2.T)[0, 0] / (n1 * n2))
        except Exception:
            return -1.0


_DETECTOR_SINGLETON: Optional[YuNetDetector] = None
_RECOGNIZER_SINGLETON: Optional[SFaceRecognizer] = None


def get_yunet_detector() -> YuNetDetector:
    global _DETECTOR_SINGLETON
    if _DETECTOR_SINGLETON is None:
        _DETECTOR_SINGLETON = YuNetDetector()
    return _DETECTOR_SINGLETON


def get_sface_recognizer() -> SFaceRecognizer:
    global _RECOGNIZER_SINGLETON
    if _RECOGNIZER_SINGLETON is None:
        _RECOGNIZER_SINGLETON = SFaceRecognizer()
    return _RECOGNIZER_SINGLETON


__all__ = [
    "YuNetDetector",
    "SFaceRecognizer",
    "get_yunet_detector",
    "get_sface_recognizer",
]

