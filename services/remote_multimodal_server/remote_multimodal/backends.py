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
        self.ocr: Optional[Any] = None
        self.ocr_backend_name: str = ""
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

        if cfg.enable_ocr:
            self._init_ocr(cfg)

    def _init_ocr(self, cfg: RuntimeConfig) -> None:
        backend = (cfg.ocr_backend or "auto").lower()
        langs = [l.strip() for l in (cfg.ocr_languages or "en").split(",") if l.strip()]

        if backend in {"auto", "paddleocr"}:
            try:
                from paddleocr import PaddleOCR  # type: ignore

                paddle_lang = langs[0] if langs else "en"
                if paddle_lang.lower() == "tr":
                    paddle_lang = "latin"
                self.ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
                self.ocr_backend_name = "paddleocr"
                logger.info("PaddleOCR loaded (lang=%s).", paddle_lang)
                return
            except Exception as exc:
                logger.info("PaddleOCR unavailable: %s", exc)

        if backend in {"auto", "easyocr"}:
            try:
                import easyocr  # type: ignore

                gpu = bool(_torch_cuda_available())
                self.ocr = easyocr.Reader(langs or ["en"], gpu=gpu)
                self.ocr_backend_name = "easyocr"
                logger.info("EasyOCR loaded (langs=%s, gpu=%s).", langs, gpu)
                return
            except Exception as exc:
                logger.info("EasyOCR unavailable: %s", exc)

        if backend in {"auto", "tesseract"}:
            try:
                import pytesseract  # type: ignore

                self.ocr = pytesseract
                self.ocr_backend_name = "tesseract"
                logger.info("pytesseract loaded.")
                return
            except Exception as exc:
                logger.info("pytesseract unavailable: %s", exc)


def _torch_cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False
