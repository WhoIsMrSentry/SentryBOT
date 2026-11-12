from __future__ import annotations

from contextlib import nullcontext
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from .backends import Backends
from .config import RuntimeConfig
from .cv_pipelines import MultiModalCVPipelinesMixin
from .models import KnownFace, known_face_from_dict, known_face_to_dict
from .onsensor_hints import HINTS_SCHEMA, hint_hazard_types, parse_onsensor_hints
from .qwen_client import QwenVlmClient

logger = logging.getLogger("remote_multimodal.engine")


class MultiModalEngine(MultiModalCVPipelinesMixin):
    def __init__(self, cfg: RuntimeConfig, *, lazy_backends: bool = False) -> None:
        self.cfg = cfg
        self._apply_profile_defaults()
        self.backends = Backends(cfg, lazy=lazy_backends)
        self.qwen = QwenVlmClient(cfg)
        self._lock = threading.RLock()
        self._inference_sem = threading.Semaphore(max(1, int(getattr(cfg, "max_concurrent_inferences", 2))))
        self._prev_gray = None
        self._prev_hist = None
        self._known_faces: List[KnownFace] = []
        self._db_path = Path(cfg.face_db_path)
        self._face_cascade = None
        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            self._face_cascade = cascade if not cascade.empty() else None  # cv2>=5 wheels dropped data xmls
        except Exception:
            pass
        self._body_hog = None
        try:
            hog = getattr(cv2, "HOGDescriptor", None)
            if hog is not None:
                self._body_hog = hog()
                self._body_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception:  # cv2>=5 wheels dropped HOGDescriptor
            self._body_hog = None
        self._load_face_db()

    def ensure_ready(self) -> None:
        if hasattr(self.backends, "ensure_loaded"):
            self.backends.ensure_loaded()

    def _lock_obj(self) -> Any:
        lock = getattr(self, "_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._lock = lock
        return lock

    def _gpu_slot(self) -> Any:
        sem = getattr(self, "_inference_sem", None)
        return sem if sem is not None else nullcontext()

    def _apply_profile_defaults(self) -> None:
        profile = str(self.cfg.runtime_profile or "balanced").strip().lower()
        overridden = set(getattr(self.cfg, "env_overrides", set()) or ())

        def _set_if_not_overridden(attr: str, val: Any) -> None:
            if attr not in overridden:
                setattr(self.cfg, attr, val)

        if profile == "ultra_fast":
            _set_if_not_overridden("yolo_conf", 0.35)
            _set_if_not_overridden("yolo_imgsz", 416)
            _set_if_not_overridden("motion_threshold", 0.1)
            _set_if_not_overridden("scene_change_threshold", 0.4)
            _set_if_not_overridden("enable_age_emotion", False)
            _set_if_not_overridden("enable_advanced_caption", False)
            if "qwen_num_predict" not in overridden:
                self.cfg.qwen_num_predict = min(self.cfg.qwen_num_predict, 120)
            if "qwen_timeout_s" not in overridden:
                self.cfg.qwen_timeout_s = min(self.cfg.qwen_timeout_s, 5.0)
        elif profile == "max_accuracy":
            _set_if_not_overridden("yolo_conf", 0.2)
            _set_if_not_overridden("yolo_imgsz", 960)
            _set_if_not_overridden("motion_threshold", 0.06)
            _set_if_not_overridden("scene_change_threshold", 0.3)
            if "qwen_num_predict" not in overridden:
                self.cfg.qwen_num_predict = max(self.cfg.qwen_num_predict, 256)
            if "qwen_timeout_s" not in overridden:
                self.cfg.qwen_timeout_s = max(self.cfg.qwen_timeout_s, 10.0)
        else:
            _set_if_not_overridden("yolo_conf", 0.25)
            _set_if_not_overridden("yolo_imgsz", 640)
            _set_if_not_overridden("motion_threshold", 0.08)
            _set_if_not_overridden("scene_change_threshold", 0.35)
            if "qwen_num_predict" not in overridden:
                self.cfg.qwen_num_predict = max(160, min(self.cfg.qwen_num_predict, 224))
            if "qwen_timeout_s" not in overridden:
                self.cfg.qwen_timeout_s = max(6.0, min(self.cfg.qwen_timeout_s, 9.0))

    def _load_face_db(self) -> None:
        if not self._db_path.exists():
            return
        with self._lock_obj():
            try:
                raw = json.loads(self._db_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self._known_faces = [f for f in (known_face_from_dict(x) for x in raw) if f is not None]
            except Exception as exc:
                logger.warning("Failed to load face db: %s", exc)

    def _save_face_db(self) -> None:
        with self._lock_obj():
            try:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                payload = [known_face_to_dict(f) for f in self._known_faces]
                tmp = self._db_path.with_name(f"{self._db_path.name}.tmp.{os.getpid()}")
                tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
                os.replace(tmp, self._db_path)
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
        onsensor_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if hasattr(self, "ensure_ready"):
            self.ensure_ready()
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
        hints = parse_onsensor_hints(onsensor_hints, h, w)
        hint_people = list(hints.get("people") or []) if hints else []
        hint_dets = list(hints.get("detections") or []) if hints else []
        # Task split contract: the robot's IMX500 owns person detection;
        # when fresh person hints arrive we skip our own detector calls while
        # still allowing identity/age/emotion enrichment on the hint bbox crops.
        if hint_people:
            run_faces = False
        objects = self.detect_objects(frame) if run_objects else []
        faces = self.detect_faces(frame) if run_faces else []
        motion, scene_change = self.motion_scene_change(frame)
        if run_qwen and self.cfg.enable_qwen_vlm:
            try:
                qwen_out = self.qwen.analyze_frame(
                    frame, question=question, semantic_reason=semantic_reason, image_b64=image_b64
                )
            except TypeError:
                qwen_out = self.qwen.analyze_frame(frame, question=question, semantic_reason=semantic_reason)
        else:
            qwen_out = {"ok": False}
        ocr_payload: Dict[str, Any] = {"ok": False}
        if run_ocr:
            ocr_payload = self.ocr_frame(frame)

        objects_out: List[Dict[str, Any]] = []
        for o in objects:
            if not isinstance(o, dict):
                continue
            entry = dict(o)
            entry.setdefault("source", "remote_cv")
            objects_out.append(entry)
        objects_out.extend(
            det for det in hint_dets if str(det.get("label", "")) != "person"
        )

        rgb_frame = (
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if (getattr(self.backends, "face_recognition", None) is not None and (faces or hint_people))
            else None
        )

        people: List[Dict[str, Any]] = []
        # Priority 1: onsensor person boxes are detection ground truth; enrich identity/emotion if backends loaded
        for hp in hint_people:
            bbox = list(hp.get("bbox_xyxy") or [])
            name = "Unknown"
            conf = float(hp.get("confidence", 0.0) or 0.0)
            age: Optional[int] = None
            emotion = ""
            if len(bbox) == 4:
                x1 = max(0, min(w - 1, int(bbox[0])))
                y1 = max(0, min(h - 1, int(bbox[1])))
                x2 = max(0, min(w, int(bbox[2])))
                y2 = max(0, min(h, int(bbox[3])))
                if x2 > x1 and y2 > y1:
                    if getattr(self.backends, "face_recognition", None) is not None:
                        try:
                            rec_name, rec_conf = self.recognize_person(frame, [x1, y1, x2, y2], rgb_frame=rgb_frame)
                        except TypeError:
                            rec_name, rec_conf = self.recognize_person(frame, [x1, y1, x2, y2])
                        if rec_name != "Unknown":
                            name = rec_name
                            conf = max(conf, float(rec_conf))
                    if getattr(self.backends, "deepface", None) is not None:
                        age, emo_val = self.estimate_age_emotion(frame[y1:y2, x1:x2])
                        emotion = emo_val or ""
            rec_level = 2 if name != "Unknown" else 0
            people.append(
                {
                    "name": name,
                    "confidence": round(conf, 3),
                    "bbox": bbox,
                    "emotion": emotion,
                    "age": age,
                    "recognition_level": rec_level,
                    "relationship": "known" if rec_level >= 2 else "unknown",
                    "track_id": hp.get("track_id"),
                    "source": "onsensor",
                }
            )
        # Priority 2: only when no hints carried people, fall back to our CV.
        for fb in faces:
            x1, y1, x2, y2 = fb
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w, x2))
            y2 = max(0, min(h, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            try:
                name, conf = self.recognize_person(frame, [x1, y1, x2, y2], rgb_frame=rgb_frame)
            except TypeError:
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
                    "source": "remote_cv",
                }
            )

        hazards = []
        seen_hazard = {"knife", "fire", "scissors"}
        for o in objects_out:
            lbl = str(o.get("label", "")).lower()
            if lbl in seen_hazard:
                hazards.append({"type": lbl, "severity": "high", "bbox": o.get("bbox"), "source": str(o.get("source", "remote_cv"))})
        for htype in hint_hazard_types(hint_dets):
            if htype not in {str(x.get("type", "")).lower() for x in hazards}:
                hazards.append({"type": htype, "severity": "high", "source": "onsensor"})
        for hz in qwen_out.get("hazards", []) if qwen_out.get("ok") else []:
            if isinstance(hz, dict):
                hz_name = str(hz.get("type") or hz.get("label") or "").strip().lower()
                sev = str(hz.get("severity") or "medium").strip().lower()
                hbbox = hz.get("bbox")
            else:
                hz_name = str(hz).strip().lower()
                sev = "medium"
                hbbox = None
            if hz_name and hz_name not in {str(x.get("type", "")).lower() for x in hazards}:
                hazards.append({"type": hz_name, "severity": sev, "bbox": hbbox})

        caption = self._caption(frame) if (mode == "semantic" or run_qwen) else None
        qwen_summary = str(qwen_out.get("summary", "")).strip() if qwen_out.get("ok") else ""
        summary = qwen_summary or caption or f"{len(people)} person, {len(objects_out)} objects."
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
            "objects": objects_out,
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
            "sources": {
                "onsensor_detections": len(hint_dets),
                "onsensor_people": len(hint_people),
                "remote_objects": len(objects_out),
                "remote_people": sum(1 for p in people if p.get("source") == "remote_cv"),
                "qwen": bool(qwen_out.get("ok")),
                "hints_schema": HINTS_SCHEMA if hints else "",
            },
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
                "onsensor_hints": bool(hints),
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
        onsensor_hints: Optional[Dict[str, Any]] = None,
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
            onsensor_hints=onsensor_hints,
        )

    def analyze_semantic(
        self,
        image_b64: str,
        requested_tasks: Optional[List[str]] = None,
        semantic_reason: str = "",
        request_id: str = "",
        question: str = "",
        onsensor_hints: Optional[Dict[str, Any]] = None,
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
            onsensor_hints=onsensor_hints,
        )
