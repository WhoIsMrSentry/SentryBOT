from __future__ import annotations

import base64
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .backends import Backends
from .config import RuntimeConfig
from .models import KnownFace

logger = logging.getLogger("remote_multimodal.cv")


class MultiModalCVPipelinesMixin:
    """Computer vision pipelines for face, object, motion, caption, and OCR detection."""

    cfg: RuntimeConfig
    backends: Backends
    _lock: threading.Lock
    _prev_gray: Optional[np.ndarray]
    _prev_hist: Optional[np.ndarray]
    _known_faces: List[KnownFace]
    _face_cascade: Any
    _body_hog: Any

    @staticmethod
    def decode_image(image_b64: str) -> np.ndarray:
        raw = base64.b64decode(image_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("invalid image_b64")
        return frame

    def detect_objects(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        if self.backends.yolo is not None:
            try:
                res = self.backends.yolo.predict(
                    frame,
                    verbose=False,
                    conf=float(self.cfg.yolo_conf),
                    imgsz=int(self.cfg.yolo_imgsz),
                )
                if res:
                    r0 = res[0]
                    boxes = getattr(r0, "boxes", None)
                    names = getattr(r0, "names", {}) or {}
                    if boxes is not None:
                        xyxy = boxes.xyxy.cpu().numpy().astype(int)
                        conf = boxes.conf.cpu().numpy()
                        cls = boxes.cls.cpu().numpy().astype(int)
                        out: List[Dict[str, Any]] = []
                        for i in range(len(xyxy)):
                            x1, y1, x2, y2 = [int(v) for v in xyxy[i]]
                            label = str(names.get(int(cls[i]), f"class_{int(cls[i])}"))
                            out.append(
                                {
                                    "label": label,
                                    "confidence": round(float(conf[i]), 3),
                                    "bbox": [x1, y1, x2, y2],
                                }
                            )
                        return out
            except Exception as exc:
                logger.debug("YOLO detect failed: %s", exc)

        rects, weights = self._body_hog.detectMultiScale(
            frame,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        out: List[Dict[str, Any]] = []
        for i, (x, y, w, h) in enumerate(rects):
            out.append(
                {
                    "label": "person",
                    "confidence": round(float(weights[i]) if i < len(weights) else 0.4, 3),
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                }
            )
        return out

    def detect_faces(self, frame: np.ndarray) -> List[List[int]]:
        fr = self.backends.face_recognition
        if fr is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                locs = fr.face_locations(rgb, model="hog")
                return [[int(l[3]), int(l[0]), int(l[1]), int(l[2])] for l in locs]
            except Exception:
                pass
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(56, 56))
        return [[int(x), int(y), int(x + w), int(y + h)] for (x, y, w, h) in faces]

    def recognize_person(self, frame: np.ndarray, face_box: List[int]) -> Tuple[str, float]:
        fr = self.backends.face_recognition
        if fr is None:
            return "Unknown", 0.0
        x1, y1, x2, y2 = face_box
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            enc = fr.face_encodings(rgb, [(y1, x2, y2, x1)])
            if not enc:
                return "Unknown", 0.0
            vec = enc[0]
            best_name = "Unknown"
            best_dist = 999.0
            for known in self._known_faces:
                dist = np.linalg.norm(np.array(known.embedding) - vec)
                if dist < best_dist:
                    best_dist = float(dist)
                    best_name = known.name
            if best_dist < 0.55:
                conf = max(0.0, min(1.0, 1.0 - (best_dist / 0.75)))
                return best_name, conf
            return "Unknown", max(0.0, min(0.5, 1.0 - (best_dist / 1.2)))
        except Exception:
            return "Unknown", 0.0

    def estimate_age_emotion(self, face_img: np.ndarray) -> Tuple[Optional[int], Optional[str]]:
        deepface = self.backends.deepface
        if deepface is None:
            return None, None
        try:
            analysis = deepface.analyze(face_img, actions=["age", "emotion"], enforce_detection=False)
            data = analysis[0] if isinstance(analysis, list) and analysis else analysis
            age = int(data.get("age")) if isinstance(data, dict) and data.get("age") is not None else None
            emotion = str(data.get("dominant_emotion")) if isinstance(data, dict) and data.get("dominant_emotion") else None
            return age, emotion
        except Exception:
            return None, None

    def motion_scene_change(self, frame: np.ndarray) -> Tuple[float, float]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        cv2.normalize(hist, hist)
        motion = 0.0
        scene = 0.0
        with self._lock:
            if self._prev_gray is not None:
                diff = cv2.absdiff(gray, self._prev_gray)
                motion = float(np.mean(diff) / 255.0)
            if self._prev_hist is not None:
                corr = cv2.compareHist(hist, self._prev_hist, cv2.HISTCMP_CORREL)
                scene = max(0.0, min(1.0, 1.0 - float(corr)))
            self._prev_gray = gray
            self._prev_hist = hist
        return motion, scene

    def _caption(self, frame: np.ndarray) -> Optional[str]:
        pipe = self.backends.caption_pipe
        if pipe is None:
            return None
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            out = pipe(rgb)
            if isinstance(out, list) and out and isinstance(out[0], dict):
                text = str(out[0].get("generated_text", "")).strip()
                return text or None
        except Exception:
            return None
        return None

    def ocr_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        ocr = self.backends.ocr
        backend = self.backends.ocr_backend_name
        if ocr is None or not backend:
            return {"ok": False, "error": "ocr_backend_unavailable", "text": "", "lines": []}
        try:
            if backend == "paddleocr":
                results = ocr.ocr(frame, cls=True)
                lines = []
                texts = []
                if results and isinstance(results, list):
                    for block in results:
                        if not block:
                            continue
                        for entry in block:
                            try:
                                bbox, (text, conf) = entry
                            except Exception:
                                continue
                            if float(conf) < self.cfg.ocr_min_confidence:
                                continue
                            lines.append({"text": str(text), "confidence": round(float(conf), 3), "bbox": [[int(p[0]), int(p[1])] for p in bbox]})
                            texts.append(str(text))
                return {"ok": True, "backend": backend, "text": " ".join(texts).strip(), "lines": lines}

            if backend == "easyocr":
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = ocr.readtext(rgb)
                lines = []
                texts = []
                for entry in results or []:
                    try:
                        bbox, text, conf = entry
                    except Exception:
                        continue
                    if float(conf) < self.cfg.ocr_min_confidence:
                        continue
                    lines.append({"text": str(text), "confidence": round(float(conf), 3), "bbox": [[int(p[0]), int(p[1])] for p in bbox]})
                    texts.append(str(text))
                return {"ok": True, "backend": backend, "text": " ".join(texts).strip(), "lines": lines}

            if backend == "tesseract":
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                text = str(ocr.image_to_string(gray) or "").strip()
                lines = [{"text": line, "confidence": 0.0, "bbox": []} for line in text.splitlines() if line.strip()]
                return {"ok": True, "backend": backend, "text": text, "lines": lines}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "text": "", "lines": []}
        return {"ok": False, "error": "unsupported_backend", "text": "", "lines": []}

    def register_face(self, name: str, image_b64: str) -> Dict[str, Any]:
        fr = self.backends.face_recognition
        if fr is None:
            return {"ok": False, "error": "face_recognition backend unavailable"}
        frame = self.decode_image(image_b64)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locs = fr.face_locations(rgb, model="hog")
        if not locs:
            return {"ok": False, "error": "no face detected"}
        enc = fr.face_encodings(rgb, [locs[0]])
        if not enc:
            return {"ok": False, "error": "face encoding failed"}
        embedding = enc[0].tolist()
        self._known_faces = [f for f in self._known_faces if f.name.lower() != name.lower()]
        self._known_faces.append(KnownFace(name=name, embedding=embedding))
        self._save_face_db()
        return {"ok": True, "name": name, "known_faces": len(self._known_faces)}
