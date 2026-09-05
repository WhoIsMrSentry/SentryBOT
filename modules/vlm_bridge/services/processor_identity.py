from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

from .processor_follow import _clamp

try:
    from .vision_event_bus import (
        EVENT_HAZARD_DETECTED,
        EVENT_NEW_PERSON,
        EVENT_OWNER_SEEN,
        EVENT_PERSON_LOST,
        EVENT_PERSON_SEEN,
    )
except Exception:
    EVENT_HAZARD_DETECTED = "hazard_detected"
    EVENT_NEW_PERSON = "new_person"
    EVENT_OWNER_SEEN = "owner_seen"
    EVENT_PERSON_LOST = "person_lost"
    EVENT_PERSON_SEEN = "person_seen"

from .processor_identity_events import ProcessorIdentityEventsMixin

logger = logging.getLogger("vlm_bridge.identity")


class ProcessorIdentityMixin(ProcessorIdentityEventsMixin):
    """Face, person identification, OCR, on-sensor, alerts and interaction logic."""

    face_manager: Optional[Any]
    _face_cascade: Optional[Any]
    _face_emotion: Optional[Any]
    event_bus: Optional[Any]
    _visible_persons: set[str]
    mode_flags: Dict[str, bool]
    mode_categories: Dict[str, Dict[str, bool]]
    _onsensor_bus: Optional[Any]
    _onsensor_unsub: Optional[Callable[[], None]]
    _onsensor_lock: threading.Lock
    _latest_onsensor: Optional[Any]
    config: Dict[str, Any]
    semantic: Any
    memory: Any
    last_blind_announcement: float
    last_alert_announcement: float
    _last_person_greet: Dict[str, float]
    person_identity: Optional[Any]
    _gateway_base: str
    _frame_lock: threading.Lock
    _latest_raw_frame: Optional[Any]
    processing_mode: str
    camera_source: Any
    remote_mm_enabled: bool
    remote_mm_ocr_endpoint: str
    remote_mm_ocr_timeout_s: float
    remote_mm_ocr_languages: List[str]
    remote_mm_auth_token: str

    def _identify_face_in_roi(self, face_roi: Any) -> Tuple[str, float]:
        if self.face_manager is None:
            return "Unknown", 0.5
        try:
            if hasattr(self.face_manager, "identify_face_with_score"):
                name, score = self.face_manager.identify_face_with_score(face_roi)
                return name, max(0.0, min(1.0, float(score)))
            name = self.face_manager.identify_face(face_roi)
            return name, 0.9 if name != "Unknown" else 0.5
        except Exception as exc:
            logger.debug("face identify failed: %s", exc)
            return "Unknown", 0.5

    def _annotate_face(
        self, annotated: Any, x1: int, y1: int, x2: int, y2: int, name: str, conf: float, distance: Optional[float], tracked: bool
    ) -> None:
        if cv2 is None:
            return
        color = (60, 180, 255) if tracked else ((255, 100, 40) if name != "Unknown" else (0, 220, 0))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = name if name != "Unknown" else "person"
        tag = f"{label} {conf:.2f}"
        if distance is not None:
            tag += f" {distance:.1f}m"
        if tracked:
            tag += " [CSRT]"
        cv2.putText(annotated, tag, (x1, max(14, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    def _process_face_boxes(self, frame: Any, boxes: List[Tuple[int, int, int, int]], tracked_box: Optional[Tuple[int, int, int, int]] = None) -> Tuple[List[Dict[str, Any]], Any]:
        parsed: List[Dict[str, Any]] = []
        annotated = frame.copy() if hasattr(frame, "copy") else frame
        current_keys: set[str] = set()
        for idx, bbox in enumerate(boxes):
            x1, y1, x2, y2 = bbox
            if x2 <= x1 or y2 <= y1:
                continue
            face_roi = frame[y1:y2, x1:x2]
            name, conf = self._identify_face_in_roi(face_roi)
            distance = self._estimate_face_distance_m(y2 - y1)
            emotion = ""
            if self._face_emotion is not None and face_roi is not None and getattr(face_roi, "size", 1):
                fer = self._face_emotion.estimate(face_roi)
                emotion = str(fer.get("emotion", "") or "")
            tracked = bool(tracked_box is not None and idx == 0)
            parsed.append(
                {
                    "label": "person",
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2],
                    "distance_m": distance,
                    "name": name,
                    "emotion": emotion,
                    "tracked": tracked,
                }
            )
            person_key = str(name or f"anon_{idx}")
            current_keys.add(person_key)
            if self.event_bus is not None and person_key not in self._visible_persons:
                self.event_bus.publish(EVENT_PERSON_SEEN, {"name": name, "emotion": emotion})
            self._annotate_face(annotated, x1, y1, x2, y2, name, conf, distance, tracked)
        if self.event_bus is not None:
            for key in self._visible_persons - current_keys:
                self.event_bus.publish(EVENT_PERSON_LOST, {"name": key})
            self._visible_persons = current_keys
        return parsed, annotated

    def _analyze_frame(self, frame: Any, enable_follow: bool) -> Tuple[List[Dict[str, Any]], Any]:
        tracked_box = None
        boxes: List[Tuple[int, int, int, int]] = []
        onsensor_active = self._onsensor_active()

        if enable_follow and getattr(self, "_follow_active", False):
            tracked_box = self._update_tracker(frame)
            if tracked_box is not None:
                boxes = [tracked_box]
        if not boxes and onsensor_active:
            boxes = self._onsensor_boxes_for_label(frame.shape, "person")
        if not boxes and not onsensor_active:
            boxes = self._detect_face_boxes(frame)

        parsed, annotated = self._process_face_boxes(frame, boxes, tracked_box)

        if enable_follow and getattr(self, "_follow_active", False):
            if getattr(self, "_follow_tracker", None) is None and parsed:
                self._lock_tracker_from_candidates(frame, parsed)
            self._drive_follow(parsed, frame.shape)

        if not self.mode_flags.get("people", True):
            parsed = []
        elif not self.mode_flags.get("faces", True):
            for item in parsed:
                item["name"] = "Unknown"

        return parsed, annotated

    def _detect_face_boxes(self, frame: Any) -> List[Tuple[int, int, int, int]]:
        if cv2 is None or self._face_cascade is None or self._face_cascade.empty():
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = self._face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.12,
                minNeighbors=5,
                minSize=(56, 56),
            )
        except Exception:
            return []

        out: List[Tuple[int, int, int, int]] = []
        h, w = frame.shape[:2]
        for x, y, fw, fh in faces:
            x1 = _clamp(int(x), 0, w - 1)
            y1 = _clamp(int(y), 0, h - 1)
            x2 = _clamp(int(x + fw), 0, w)
            y2 = _clamp(int(y + fh), 0, h)
            if x2 > x1 and y2 > y1:
                out.append((x1, y1, x2, y2))
        return out

    def _estimate_face_distance_m(self, box_h: int) -> Optional[float]:
        if box_h <= 0:
            return None
        distance = (0.24 * 600.0) / float(box_h)
        return round(float(distance), 2)

    def attach_onsensor_bus(self, bus: Any) -> None:
        if bus is None:
            return
        if self._onsensor_unsub is not None:
            try:
                self._onsensor_unsub()
            except Exception:
                pass
            self._onsensor_unsub = None
        self._onsensor_bus = bus
        if hasattr(bus, "subscribe"):
            try:
                self._onsensor_unsub = bus.subscribe(self._on_sensor_snapshot)
            except Exception as exc:
                logger.debug("onsensor subscribe failed: %s", exc)

    def detach_onsensor_bus(self) -> None:
        if self._onsensor_unsub is not None:
            try:
                self._onsensor_unsub()
            except Exception:
                pass
            self._onsensor_unsub = None
        self._onsensor_bus = None

    def _on_sensor_snapshot(self, snapshot: Any) -> None:
        with self._onsensor_lock:
            self._latest_onsensor = snapshot

    def _latest_onsensor_snapshot(self) -> Optional[Any]:
        with self._onsensor_lock:
            return self._latest_onsensor

    def _onsensor_active(self) -> bool:
        if self._onsensor_bus is None:
            return False
        flags = self.mode_categories.get("onsensor", {})
        return bool(flags.get("tiny_detect", False))

    def _onsensor_boxes_for_label(self, frame_shape: Tuple[int, ...], label: str) -> List[Tuple[int, int, int, int]]:
        snap = self._latest_onsensor_snapshot()
        if snap is None:
            return []
        max_age = 1.5
        try:
            if (time.time() - float(getattr(snap, "ts", 0.0))) > max_age:
                return []
        except Exception:
            return []
        h, w = frame_shape[:2]
        boxes: List[Tuple[int, int, int, int]] = []
        for det in getattr(snap, "detections", []) or []:
            if str(getattr(det, "label", "")).strip().lower() != label.strip().lower():
                continue
            bbox = getattr(det, "bbox_xyxy_norm", None)
            if not bbox or len(bbox) != 4:
                continue
            x1n, y1n, x2n, y2n = [float(v) for v in bbox]
            if max(x2n, y2n) <= 1.5:
                x1 = int(_clamp(int(x1n * w), 0, w - 1))
                y1 = int(_clamp(int(y1n * h), 0, h - 1))
                x2 = int(_clamp(int(x2n * w), 0, w))
                y2 = int(_clamp(int(y2n * h), 0, h))
            else:
                x1 = int(_clamp(int(x1n), 0, w - 1))
                y1 = int(_clamp(int(y1n), 0, h - 1))
                x2 = int(_clamp(int(x2n), 0, w))
                y2 = int(_clamp(int(y2n), 0, h))
            if x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))
        return boxes

    def _onsensor_object_results(self) -> List[Dict[str, Any]]:
        snap = self._latest_onsensor_snapshot()
        if snap is None:
            return []
        results: List[Dict[str, Any]] = []
        for det in getattr(snap, "detections", []) or []:
            label = str(getattr(det, "label", "")).strip()
            if not label or label.lower() == "person":
                continue
            bbox = list(getattr(det, "bbox_xyxy_norm", []) or [])
            results.append(
                {
                    "label": label,
                    "confidence": float(getattr(det, "score", 0.0) or 0.0),
                    "bbox": bbox,
                    "distance_m": None,
                    "name": "",
                    "source": "imx500",
                }
            )
        return results

    def register_face_from_current_frame(self, name: str) -> bool:
        if not self.face_manager or self.processing_mode != "local":
            return False
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()
        if frame is None and not (isinstance(self.camera_source, str) and self.camera_source.lower().startswith(("http://", "https://"))):
            try:
                cap = cv2.VideoCapture(self.camera_source)
                if cap.isOpened():
                    ok, snap = cap.read()
                    cap.release()
                    if ok and snap is not None:
                        frame = snap
            except Exception:
                pass
        if frame is None:
            return False
        return bool(self.face_manager.register_face(name, frame))
