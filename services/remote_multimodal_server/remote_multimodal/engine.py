from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from .backends import Backends
from .config import RuntimeConfig
from .cv_pipelines import MultiModalCVPipelinesMixin
from .models import KnownFace, known_face_from_dict, known_face_to_dict
from .qwen_client import QwenVlmClient

logger = logging.getLogger("remote_multimodal.engine")


class MultiModalEngine(MultiModalCVPipelinesMixin):
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self._apply_profile_defaults()
        self.backends = Backends(cfg)
        self.qwen = QwenVlmClient(cfg)
        self._lock = threading.Lock()
        self._prev_gray = None
        self._prev_hist = None
        self._known_faces: List[KnownFace] = []
        self._db_path = Path(cfg.face_db_path)
        self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._body_hog = cv2.HOGDescriptor()
        self._body_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._load_face_db()

    def _apply_profile_defaults(self) -> None:
        profile = str(self.cfg.runtime_profile or "balanced").strip().lower()
        if profile == "ultra_fast":
            self.cfg.yolo_conf = 0.35
            self.cfg.yolo_imgsz = 416
            self.cfg.motion_threshold = 0.1
            self.cfg.scene_change_threshold = 0.4
            self.cfg.enable_age_emotion = False
            self.cfg.enable_advanced_caption = False
            self.cfg.qwen_num_predict = min(self.cfg.qwen_num_predict, 120)
            self.cfg.qwen_timeout_s = min(self.cfg.qwen_timeout_s, 5.0)
        elif profile == "max_accuracy":
            self.cfg.yolo_conf = 0.2
            self.cfg.yolo_imgsz = 960
            self.cfg.motion_threshold = 0.06
            self.cfg.scene_change_threshold = 0.3
            self.cfg.qwen_num_predict = max(self.cfg.qwen_num_predict, 256)
            self.cfg.qwen_timeout_s = max(self.cfg.qwen_timeout_s, 10.0)
        else:
            self.cfg.yolo_conf = 0.25
            self.cfg.yolo_imgsz = 640
            self.cfg.motion_threshold = 0.08
            self.cfg.scene_change_threshold = 0.35
            self.cfg.qwen_num_predict = max(160, min(self.cfg.qwen_num_predict, 224))
            self.cfg.qwen_timeout_s = max(6.0, min(self.cfg.qwen_timeout_s, 9.0))

    def _load_face_db(self) -> None:
        if not self._db_path.exists():
            return
        try:
            raw = json.loads(self._db_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self._known_faces = [f for f in (known_face_from_dict(x) for x in raw) if f is not None]
        except Exception as exc:
            logger.warning("Failed to load face db: %s", exc)

    def _save_face_db(self) -> None:
        try:
            payload = [known_face_to_dict(f) for f in self._known_faces]
            self._db_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save face db: %s", exc)

    @staticmethod
    def _should_run_qwen(allow: set[str], run_semantic_vlm: Optional[bool]) -> bool:
        if run_semantic_vlm is not None:
            return bool(run_semantic_vlm)
        return (not allow) or ("semantic_scene" in allow) or ("hazards" in allow)

    def analyze(
        self,
        image_b64: str,
        requested_tasks: Optional[List[str]] = None,
        run_semantic_vlm: Optional[bool] = None,
        semantic_reason: str = "",
        request_id: str = "",
        question: str = "",
        task_mode: str = "",
    ) -> Dict[str, Any]:
        frame = self.decode_image(image_b64)
        h, w = frame.shape[:2]
        allow = {str(t).strip().lower() for t in (requested_tasks or []) if str(t).strip()}
        mode = str(task_mode or "").strip().lower()
        run_objects = (not allow) or ("objects" in allow) or ("hazards" in allow)
        run_faces = (not allow) or ("faces" in allow) or ("people" in allow)
        run_ocr = ("ocr" in allow) if allow else False
        run_qwen = self._should_run_qwen(allow, run_semantic_vlm)
        if mode not in {"cheap", "semantic", "legacy"}:
            mode = "semantic" if run_qwen else ("cheap" if allow else "legacy")
        objects = self.detect_objects(frame) if run_objects else []
        faces = self.detect_faces(frame) if run_faces else []
        motion, scene_change = self.motion_scene_change(frame)
        qwen_out = self.qwen.analyze_frame(frame) if (run_qwen and self.cfg.enable_qwen_vlm) else {"ok": False}
        ocr_payload: Dict[str, Any] = {"ok": False}
        if run_ocr:
            ocr_payload = self.ocr_frame(frame)

        people: List[Dict[str, Any]] = []
        for fb in faces:
            x1, y1, x2, y2 = fb
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w, x2))
            y2 = max(0, min(h, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            name, conf = self.recognize_person(frame, [x1, y1, x2, y2])
            age, emotion = self.estimate_age_emotion(crop)
            rec_level = 2 if name != "Unknown" else 0
            people.append(
                {
                    "name": name,
                    "confidence": round(float(conf), 3),
                    "bbox": [x1, y1, x2, y2],
                    "emotion": emotion,
                    "age": age,
                    "recognition_level": rec_level,
                    "relationship": "known" if rec_level >= 2 else "unknown",
                }
            )

        hazards = []
        for o in objects:
            lbl = str(o.get("label", "")).lower()
            if lbl in {"knife", "fire", "scissors"}:
                hazards.append({"type": lbl, "severity": "high", "bbox": o.get("bbox")})
        for hz in qwen_out.get("hazards", []) if qwen_out.get("ok") else []:
            hz_name = str(hz).strip().lower()
            if hz_name and hz_name not in {str(x.get("type", "")).lower() for x in hazards}:
                hazards.append({"type": hz_name, "severity": "medium", "bbox": None})

        caption = self._caption(frame)
        qwen_summary = str(qwen_out.get("summary", "")).strip() if qwen_out.get("ok") else ""
        summary = qwen_summary or caption or f"{len(people)} person, {len(objects)} objects."
        if scene_change > self.cfg.scene_change_threshold:
            summary += " Scene changed."
        if motion > self.cfg.motion_threshold:
            summary += " Motion detected."
        if hazards:
            summary += " Hazard present."
        persona_interpretation = (
            str(qwen_out.get("persona_interpretation", "")).strip() if qwen_out.get("ok") else ""
        ) or summary.strip()
        suggested_focus = (
            str(qwen_out.get("suggested_focus", "")).strip() if qwen_out.get("ok") else ""
        )
        focus_type = "person" if people else "scene"
        if suggested_focus in {"person", "face", "human"}:
            focus_type = "person"
        elif suggested_focus in {"hazard", "danger", "object"} and hazards:
            focus_type = "hazard"

        importance = 0.35 + (0.2 if people else 0.0) + (0.15 if scene_change > self.cfg.scene_change_threshold else 0.0) + (0.1 if motion > self.cfg.motion_threshold else 0.0) + (0.3 if hazards else 0.0)
        if qwen_out.get("ok"):
            importance += 0.1
        return {
            "ok": True,
            "summary": summary.strip(),
            "persona_interpretation": persona_interpretation,
            "objects": objects,
            "people": people,
            "hazards": hazards,
            "motion": {"score": round(motion, 3), "detected": motion > self.cfg.motion_threshold},
            "scene_change": {"score": round(scene_change, 3), "changed": scene_change > self.cfg.scene_change_threshold},
            "interesting_events": ["scene_changed"] if scene_change > self.cfg.scene_change_threshold else [],
            "recommended_focus": {"type": focus_type, "reason": "hybrid_cv_qwen" if qwen_out.get("ok") else "cheap_cv"},
            "importance_score": round(min(1.0, max(0.0, importance)), 3),
            "frame_size": {"w": int(w), "h": int(h)},
            "ocr": ocr_payload,
            "requested_tasks": sorted(allow) if allow else [],
            "backend_info": {
                "yolo": bool(self.backends.yolo is not None),
                "face_recognition": bool(self.backends.face_recognition is not None),
                "deepface": bool(self.backends.deepface is not None),
                "advanced_caption": bool(self.backends.caption_pipe is not None),
                "qwen_vlm": bool(qwen_out.get("ok")),
                "qwen_model": qwen_out.get("model", ""),
                "semantic_vlm_requested": bool(run_qwen),
                "semantic_reason": str(semantic_reason or ""),
                "request_id": str(request_id or ""),
                "question": bool(str(question or "").strip()),
                "task_mode": mode,
                "semantic_endpoint": mode == "semantic",
                "cheap_endpoint": mode == "cheap",
                "ocr": self.backends.ocr_backend_name,
            },
        }

    def analyze_cheap(
        self,
        image_b64: str,
        requested_tasks: Optional[List[str]] = None,
        semantic_reason: str = "",
        request_id: str = "",
        question: str = "",
    ) -> Dict[str, Any]:
        tasks = requested_tasks or ["objects", "people", "faces", "hazards"]
        return self.analyze(
            image_b64,
            requested_tasks=tasks,
            run_semantic_vlm=False,
            semantic_reason=semantic_reason or "cheap_poll",
            request_id=request_id,
            question=question,
            task_mode="cheap",
        )

    def analyze_semantic(
        self,
        image_b64: str,
        requested_tasks: Optional[List[str]] = None,
        semantic_reason: str = "",
        request_id: str = "",
        question: str = "",
    ) -> Dict[str, Any]:
        base = list(requested_tasks or ["objects", "people", "faces", "hazards", "semantic_scene"])
        if "semantic_scene" not in {str(t).strip().lower() for t in base}:
            base.append("semantic_scene")
        return self.analyze(
            image_b64,
            requested_tasks=base,
            run_semantic_vlm=True,
            semantic_reason=semantic_reason or "semantic_request",
            request_id=request_id,
            question=question,
            task_mode="semantic",
        )
