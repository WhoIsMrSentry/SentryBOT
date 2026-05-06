from __future__ import annotations

import logging
from typing import Any, Optional

from .config import RuntimeConfig

logger = logging.getLogger("remote_multimodal.backends")


class Backends:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.yolo: Optional[Any] = None
        self.face_recognition: Optional[Any] = None
        self.deepface: Optional[Any] = None
        self.caption_pipe: Optional[Any] = None
        self._init(cfg)

    def _init(self, cfg: RuntimeConfig) -> None:
        if cfg.detector_backend in {"auto", "yolo"}:
            try:
                from ultralytics import YOLO  # type: ignore

                self.yolo = YOLO(cfg.yolo_model)
                logger.info("YOLO loaded: %s", cfg.yolo_model)
            except Exception as exc:
                logger.info("YOLO unavailable: %s", exc)

        if cfg.enable_face_recognition:
            try:
                import face_recognition  # type: ignore

                self.face_recognition = face_recognition
                logger.info("face_recognition loaded.")
            except Exception as exc:
                logger.info("face_recognition unavailable: %s", exc)

        if cfg.enable_age_emotion:
            try:
                from deepface import DeepFace  # type: ignore

                self.deepface = DeepFace
                logger.info("DeepFace loaded.")
            except Exception as exc:
                logger.info("DeepFace unavailable: %s", exc)

        # Optional image-level caption backend (can be upgraded on remote GPU host).
        if cfg.enable_advanced_caption:
            try:
                from transformers import pipeline  # type: ignore

                self.caption_pipe = pipeline(
                    task="image-to-text",
                    model=cfg.advanced_caption_model,
                )
                logger.info("Caption model loaded: %s", cfg.advanced_caption_model)
            except Exception as exc:
                logger.info("Advanced caption backend unavailable: %s", exc)
