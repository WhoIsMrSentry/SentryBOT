from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import cv2
import requests

try:
    from .face_manager import FaceManager
except Exception:
    try:
        from services.face_manager import FaceManager
    except Exception:
        FaceManager = None  # type: ignore

try:
    from .cascade_loader import load_frontal_face_cascade
except Exception:
    from services.cascade_loader import load_frontal_face_cascade  # type: ignore

try:
    from .semantic_describer import SemanticDescriber
except Exception:
    from services.semantic_describer import SemanticDescriber  # type: ignore

try:
    from .people_memory import PeopleMemory
except Exception:
    from services.people_memory import PeopleMemory  # type: ignore

try:
    from .action_dispatcher import VisionActionDispatcher
except Exception:
    from services.action_dispatcher import VisionActionDispatcher  # type: ignore

try:
    from .llm_client import generate_text
except Exception:
    from services.llm_client import generate_text  # type: ignore


logger = logging.getLogger("vlm_bridge")


def _create_csrt_tracker() -> Optional[Any]:
    if hasattr(cv2, "TrackerCSRT_create"):
        try:
            return cv2.TrackerCSRT_create()
        except Exception:
            pass
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        try:
            return legacy.TrackerCSRT_create()
        except Exception:
            pass
    return None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class VisionProcessor:
    """YOLO'suz VLM Bridge isleyici.

    Yerelde:
    - OpenCV Haar face detect
    - OpenCV ORB+FLANN ile kimliklendirme
    - CSRT ile takip

    Uzakta:
    - /vlm/results ile gelen sonuclari cache'ler.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        vision_cfg = config.get("vision", {}) if isinstance(config, dict) else {}

        self.processing_mode = str(vision_cfg.get("processing_mode", "local")).strip().lower()
        self.camera_source = vision_cfg.get("camera_source", 0)
        self.conf_threshold = float(vision_cfg.get("confidence_threshold", 0.5))

        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes", {}), dict) else {}
        self.mode_flags: Dict[str, bool] = {
            "objects": bool(raw_modes.get("objects", True)),
            "people": bool(raw_modes.get("people", True)),
            "faces": bool(raw_modes.get("faces", True)),
            "depth": bool(raw_modes.get("depth", False)),
            "ocr": bool(raw_modes.get("ocr", False)),
            "hazards": bool(raw_modes.get("hazards", True)),
            "semantic_scene": bool(raw_modes.get("semantic_scene", True)),
        }
        self.mode_profiles: Dict[str, Dict[str, bool]] = {
            "balanced": dict(self.mode_flags),
            "people_focus": {
                "objects": False,
                "people": True,
                "faces": True,
                "depth": False,
                "ocr": False,
                "hazards": True,
                "semantic_scene": True,
            },
            "objects_focus": {
                "objects": True,
                "people": False,
                "faces": False,
                "depth": False,
                "ocr": False,
                "hazards": True,
                "semantic_scene": True,
            },
            "assistive": {
                "objects": True,
                "people": True,
                "faces": True,
                "depth": bool(raw_modes.get("depth", False)),
                "ocr": bool(raw_modes.get("ocr", False)),
                "hazards": True,
                "semantic_scene": True,
            },
            "minimal": {
                "objects": False,
                "people": False,
                "faces": False,
                "depth": False,
                "ocr": False,
                "hazards": False,
                "semantic_scene": False,
            },
        }

        self._face_cascade = load_frontal_face_cascade(logger)

        self.face_manager = None
        if self.processing_mode == "local" and FaceManager is not None:
            try:
                face_match_cfg = vision_cfg.get("face_match", {}) if isinstance(vision_cfg.get("face_match", {}), dict) else {}
                self.face_manager = FaceManager(
                    ratio_test=float(face_match_cfg.get("ratio_test", 0.72)),
                    min_good_matches=int(face_match_cfg.get("min_good_matches", 10)),
                    min_score=float(face_match_cfg.get("min_score", 0.15)),
                )
            except Exception as exc:
                logger.warning("FaceManager init failed: %s", exc)

        self._stop_event = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._inference_thread: Optional[threading.Thread] = None

        self._frame_lock = threading.Lock()
        self._latest_raw_frame: Optional[Any] = None
        self._latest_annotated_frame: Optional[bytes] = None

        self.latest_results: List[Dict[str, Any]] = []
        self.blind_mode_enabled = bool(vision_cfg.get("blind_mode", {}).get("enabled", False))
        self.last_blind_announcement = 0.0
        self.last_alert_announcement = 0.0
        self._last_person_greet: Dict[str, float] = {}

        # Follow mode state (face lock + CSRT)
        follow_cfg = vision_cfg.get("follow", {}) if isinstance(vision_cfg.get("follow", {}), dict) else {}
        self._follow_cfg = {
            "enabled": bool(follow_cfg.get("enabled", True)),
            "track_interval_s": float(follow_cfg.get("track_interval_s", 0.12)),
            "pan_gain_deg": float(follow_cfg.get("pan_gain_deg", 50.0)),
            "tilt_gain_deg": float(follow_cfg.get("tilt_gain_deg", 32.0)),
            "center_pan": int(follow_cfg.get("center_pan", 90)),
            "center_tilt": int(follow_cfg.get("center_tilt", 90)),
            "min_pan": int(follow_cfg.get("min_pan", 35)),
            "max_pan": int(follow_cfg.get("max_pan", 145)),
            "min_tilt": int(follow_cfg.get("min_tilt", 65)),
            "max_tilt": int(follow_cfg.get("max_tilt", 125)),
            "max_lost_frames": int(follow_cfg.get("max_lost_frames", 18)),
        }
        self._follow_active = False
        self._follow_target: Optional[str] = None
        self._follow_tracker: Optional[Any] = None
        self._follow_lost_frames = 0
        self._follow_last_track_ts = 0.0
        self._follow_current_bbox: Optional[Tuple[int, int, int, int]] = None
        self._track_callback: Optional[Callable[..., Any]] = None

        self.semantic = SemanticDescriber(config)
        self.memory = PeopleMemory()

        actions_cfg = config.get("actions", {}) if isinstance(config, dict) else {}
        endpoint = str(actions_cfg.get("endpoint", "http://localhost:8080/autonomy/apply_actions"))
        timeout = float(actions_cfg.get("timeout", 1.5))
        enabled = bool(actions_cfg.get("default_apply", False))
        self.action_dispatcher = VisionActionDispatcher(endpoint=endpoint, timeout=timeout, enabled=enabled)

        if self.processing_mode == "local":
            logger.info("[vlm_bridge] Local mode: OpenCV face recognition + CSRT tracking active")
        else:
            logger.info("[vlm_bridge] Remote mode: waiting for /vlm/results payloads")

    def get_modes(self) -> Dict[str, bool]:
        return dict(self.mode_flags)

    def list_profiles(self) -> List[str]:
        return sorted(self.mode_profiles.keys())

    def set_modes(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        changed: Dict[str, bool] = {}
        for key, value in updates.items():
            if key in self.mode_flags:
                self.mode_flags[key] = bool(value)
                changed[key] = self.mode_flags[key]
        return {"ok": True, "changed": changed, "modes": self.get_modes()}

    def apply_mode_profile(self, name: str) -> Dict[str, Any]:
        profile = self.mode_profiles.get(str(name).strip().lower())
        if not profile:
            return {"ok": False, "error": "unknown_profile", "profiles": self.list_profiles()}
        self.mode_flags.update(profile)
        return {"ok": True, "profile": str(name).strip().lower(), "modes": self.get_modes()}

    def set_processing_mode(self, mode: str) -> Dict[str, Any]:
        m = str(mode or "").strip().lower()
        if m not in {"local", "remote"}:
            return {"ok": False, "error": "invalid_mode", "allowed": ["local", "remote"]}
        if m == self.processing_mode:
            return {"ok": True, "processing_mode": self.processing_mode}

        if m == "remote":
            self.stop_stream_processing()
            self.processing_mode = "remote"
            return {"ok": True, "processing_mode": self.processing_mode}

        # switch remote -> local
        self.processing_mode = "local"
        self.start_stream_processing()
        return {"ok": True, "processing_mode": self.processing_mode}

    # -----------------------------------------------------------------
    # Public control API
    # -----------------------------------------------------------------
    def set_track_callback(self, callback: Callable[..., Any]) -> None:
        self._track_callback = callback

    def start_follow(self, person: Optional[str] = None) -> Dict[str, Any]:
        if not self._follow_cfg.get("enabled", True):
            return {"ok": False, "error": "follow mode disabled"}

        self._follow_active = True
        self._follow_target = str(person).strip() if person else None
        self._follow_tracker = None
        self._follow_lost_frames = 0
        self._follow_current_bbox = None

        if self.processing_mode == "local":
            self.start_stream_processing()

        status = self.follow_status()
        status["ok"] = True
        return status

    def stop_follow(self) -> Dict[str, Any]:
        self._follow_active = False
        self._follow_target = None
        self._follow_tracker = None
        self._follow_lost_frames = 0
        self._follow_current_bbox = None
        return {"ok": True, **self.follow_status()}

    def follow_status(self) -> Dict[str, Any]:
        return {
            "active": bool(self._follow_active),
            "target": self._follow_target,
            "tracking": bool(self._follow_tracker is not None),
            "bbox": list(self._follow_current_bbox) if self._follow_current_bbox else None,
            "mode": self.processing_mode,
        }

    # -----------------------------------------------------------------
    # Streaming lifecycle
    # -----------------------------------------------------------------
    def start_stream_processing(self) -> None:
        if self.processing_mode != "local":
            logger.debug("start_stream_processing() ignored in remote mode")
            return
        if self._capture_thread and self._capture_thread.is_alive():
            return

        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inference_thread.start()

        logger.info("Vision processing started (OpenCV face mode)")

    def stop_stream_processing(self) -> None:
        if self.processing_mode != "local":
            return
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._inference_thread:
            self._inference_thread.join(timeout=2.0)
        logger.info("Vision processing stopped")

    def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            logger.error("Could not open camera source: %s", self.camera_source)
            return

        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Failed to read frame, retrying...")
                time.sleep(0.6)
                cap.release()
                cap = cv2.VideoCapture(self.camera_source)
                continue

            with self._frame_lock:
                self._latest_raw_frame = frame

            time.sleep(0.003)

        cap.release()

    def _inference_loop(self) -> None:
        while not self._stop_event.is_set():
            frame = None
            with self._frame_lock:
                if self._latest_raw_frame is not None:
                    frame = self._latest_raw_frame.copy()

            if frame is None:
                time.sleep(0.08)
                continue

            parsed_results, annotated = self._analyze_frame(frame, enable_follow=True)
            self.latest_results = parsed_results

            # Follow aktifken VLM sahne aksiyonu / tehlike anonsu bastirilir,
            # odak yuz kilidi ve takip akisinda kalir.
            self._handle_person_interactions(parsed_results)
            if not self._follow_active:
                self._evaluate_alerts(parsed_results)
                if parsed_results and self.mode_flags.get("semantic_scene", True):
                    self.action_dispatcher.emit_scene(self.semantic, parsed_results)
                if self.blind_mode_enabled and parsed_results:
                    self._handle_blind_mode(parsed_results)

            ok, buf = cv2.imencode(".jpg", annotated)
            if ok:
                with self._frame_lock:
                    self._latest_annotated_frame = buf.tobytes()

            time.sleep(0.05)

    # -----------------------------------------------------------------
    # Core analysis
    # -----------------------------------------------------------------
    def _analyze_frame(self, frame: Any, enable_follow: bool) -> Tuple[List[Dict[str, Any]], Any]:
        boxes: List[Tuple[int, int, int, int]] = []
        tracked_box = None

        if enable_follow and self._follow_active:
            tracked_box = self._update_tracker(frame)
            if tracked_box is not None:
                boxes = [tracked_box]
            else:
                boxes = self._detect_face_boxes(frame)
        else:
            boxes = self._detect_face_boxes(frame)

        parsed: List[Dict[str, Any]] = []
        annotated = frame.copy()
        for idx, bbox in enumerate(boxes):
            x1, y1, x2, y2 = bbox
            if x2 <= x1 or y2 <= y1:
                continue
            face_roi = frame[y1:y2, x1:x2]
            name = "Unknown"
            conf = 0.5
            if self.face_manager is not None:
                try:
                    if hasattr(self.face_manager, "identify_face_with_score"):
                        name, score = self.face_manager.identify_face_with_score(face_roi)
                        conf = max(0.0, min(1.0, float(score)))
                    else:
                        name = self.face_manager.identify_face(face_roi)
                        conf = 0.9 if name != "Unknown" else 0.5
                except Exception as exc:
                    logger.debug("face identify failed: %s", exc)

            distance = self._estimate_face_distance_m(y2 - y1)
            tracked = bool(tracked_box is not None and idx == 0)
            parsed.append(
                {
                    "label": "person",
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2],
                    "distance_m": distance,
                    "name": name,
                    "tracked": tracked,
                }
            )

            color = (0, 220, 0)
            if name != "Unknown":
                color = (255, 100, 40)
            if tracked:
                color = (60, 180, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = name if name != "Unknown" else "person"
            tag = f"{label} {conf:.2f}"
            if distance is not None:
                tag += f" {distance:.1f}m"
            if tracked:
                tag += " [CSRT]"
            cv2.putText(
                annotated,
                tag,
                (x1, max(14, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

        if enable_follow and self._follow_active:
            if self._follow_tracker is None and parsed:
                self._lock_tracker_from_candidates(frame, parsed)
            self._drive_follow(parsed, frame.shape)

        if not self.mode_flags.get("people", True):
            parsed = []
        elif not self.mode_flags.get("faces", True):
            for item in parsed:
                item["name"] = "Unknown"

        return parsed, annotated

    def _detect_face_boxes(self, frame: Any) -> List[Tuple[int, int, int, int]]:
        if self._face_cascade is None or self._face_cascade.empty():
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
        for (x, y, fw, fh) in faces:
            x1 = _clamp(int(x), 0, w - 1)
            y1 = _clamp(int(y), 0, h - 1)
            x2 = _clamp(int(x + fw), 0, w)
            y2 = _clamp(int(y + fh), 0, h)
            if x2 > x1 and y2 > y1:
                out.append((x1, y1, x2, y2))
        return out

    def _estimate_face_distance_m(self, box_h: int) -> Optional[float]:
        # Basit pinhole tahmini (yaklasik): face_h_real~0.24m, focal_px~600
        if box_h <= 0:
            return None
        distance = (0.24 * 600.0) / float(box_h)
        return round(float(distance), 2)

    def _update_tracker(self, frame: Any) -> Optional[Tuple[int, int, int, int]]:
        if self._follow_tracker is None:
            return None
        try:
            ok, box = self._follow_tracker.update(frame)
        except Exception:
            ok, box = False, None

        if not ok or box is None:
            self._follow_lost_frames += 1
            if self._follow_lost_frames >= int(self._follow_cfg.get("max_lost_frames", 18)):
                self._follow_tracker = None
                self._follow_current_bbox = None
            return None

        self._follow_lost_frames = 0
        x, y, w, h = [int(v) for v in box]
        x1, y1, x2, y2 = x, y, x + w, y + h
        self._follow_current_bbox = (x1, y1, x2, y2)
        return self._follow_current_bbox

    def _lock_tracker_from_candidates(self, frame: Any, results: List[Dict[str, Any]]) -> None:
        target_idx = 0
        target_name = str(self._follow_target or "").strip().lower()
        if target_name:
            for i, res in enumerate(results):
                name = str(res.get("name") or "").strip().lower()
                if name and name == target_name:
                    target_idx = i
                    break
        else:
            for i, res in enumerate(results):
                if str(res.get("name") or "") not in ("", "Unknown"):
                    target_idx = i
                    break

        bbox = results[target_idx].get("bbox") or []
        if len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(v) for v in bbox]
        tracker = _create_csrt_tracker()
        if tracker is None:
            return

        try:
            ok = tracker.init(frame, (x1, y1, x2 - x1, y2 - y1))
        except Exception:
            ok = False
        if not ok:
            return

        self._follow_tracker = tracker
        self._follow_lost_frames = 0
        self._follow_current_bbox = (x1, y1, x2, y2)

    def _drive_follow(self, results: List[Dict[str, Any]], frame_shape: Tuple[int, ...]) -> None:
        if not self._follow_active or not results:
            return

        now = time.time()
        if now - self._follow_last_track_ts < float(self._follow_cfg.get("track_interval_s", 0.12)):
            return

        # Takipte once tracker bbox, yoksa secili hedef kisinin bbox'i kullanilir.
        selected = None
        if self._follow_current_bbox is not None:
            for res in results:
                b = res.get("bbox") or []
                if len(b) == 4 and tuple(int(v) for v in b) == self._follow_current_bbox:
                    selected = res
                    break
        if selected is None:
            target = str(self._follow_target or "").strip().lower()
            if target:
                for res in results:
                    name = str(res.get("name") or "").strip().lower()
                    if name == target:
                        selected = res
                        break
        if selected is None:
            selected = results[0]

        bbox = selected.get("bbox") or []
        if len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame_shape[:2]
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5

        dx_norm = ((cx - (w * 0.5)) / max(1.0, w * 0.5))
        dy_norm = ((cy - (h * 0.5)) / max(1.0, h * 0.5))

        pan = int(round(float(self._follow_cfg.get("center_pan", 90)) + dx_norm * float(self._follow_cfg.get("pan_gain_deg", 50.0))))
        tilt = int(round(float(self._follow_cfg.get("center_tilt", 90)) + dy_norm * float(self._follow_cfg.get("tilt_gain_deg", 32.0))))

        pan = _clamp(pan, int(self._follow_cfg.get("min_pan", 35)), int(self._follow_cfg.get("max_pan", 145)))
        tilt = _clamp(tilt, int(self._follow_cfg.get("min_tilt", 65)), int(self._follow_cfg.get("max_tilt", 125)))

        self._send_track(pan=pan, tilt=tilt, drive=0)
        self._follow_last_track_ts = now

    def _send_track(self, pan: int, tilt: int, drive: int = 0) -> None:
        if self._track_callback is not None:
            try:
                self._track_callback(head_pan=float(pan), head_tilt=float(tilt), drive=int(drive))
                return
            except Exception as exc:
                logger.debug("track callback failed: %s", exc)

        try:
            requests.post(
                "http://localhost:8080/vlm/track",
                params={"head_pan": float(pan), "head_tilt": float(tilt), "drive": int(drive)},
                timeout=0.25,
            )
        except Exception:
            pass

    # -----------------------------------------------------------------
    # API-compatible helpers
    # -----------------------------------------------------------------
    def generate_frames(self) -> Generator[bytes, None, None]:
        while True:
            frame = None
            with self._frame_lock:
                frame = self._latest_annotated_frame

            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(0.05)

    def analyze_snapshot(self) -> List[Dict[str, Any]]:
        if self.processing_mode != "local":
            return [{"error": "Local analysis disabled in remote mode"}]

        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            return [{"error": "Could not open camera"}]
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return [{"error": "Failed to capture frame"}]

        results, _annotated = self._analyze_frame(frame, enable_follow=False)
        return results

    def register_face_from_current_frame(self, name: str) -> bool:
        if not self.face_manager or self.processing_mode != "local":
            return False
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()
        if frame is None:
            return False
        return bool(self.face_manager.register_face(name, frame))

    # -----------------------------------------------------------------
    # Remote ingestion
    # -----------------------------------------------------------------
    def ingest_remote_results(self, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Follow modunda uzak VLM nesne akisi bastirilir.
        if self._follow_active:
            return {"count": 0, "skipped": "follow_active"}

        normalized: List[Dict[str, Any]] = []
        for o in objects:
            if not isinstance(o, dict):
                continue
            label = o.get("label") or o.get("name") or "unknown"
            conf = float(o.get("confidence", o.get("conf", 0.0)) or 0.0)
            bbox = o.get("bbox") or o.get("box") or []
            distance = o.get("distance_m") if o.get("distance_m") is not None else o.get("distance")
            normalized.append(
                {
                    "label": label,
                    "confidence": conf,
                    "bbox": bbox,
                    "distance_m": distance,
                    "name": o.get("name", "Unknown"),
                }
            )

        if not self.mode_flags.get("objects", True):
            normalized = [r for r in normalized if str(r.get("label", "")).lower() == "person"]
        if not self.mode_flags.get("people", True):
            normalized = [r for r in normalized if str(r.get("label", "")).lower() != "person"]
        if not self.mode_flags.get("faces", True):
            for item in normalized:
                item["name"] = "Unknown"

        self.latest_results = normalized
        self._evaluate_alerts(normalized)
        self._handle_person_interactions(normalized)
        if self.blind_mode_enabled and normalized:
            self._handle_blind_mode(normalized)
        if normalized and self.mode_flags.get("semantic_scene", True):
            self.action_dispatcher.emit_scene(self.semantic, normalized)
        return {"count": len(normalized)}

    def record_chat(self, person: str, text: str, role: str = "assistant") -> None:
        self.memory.append_chat(person, role, text)

    # -----------------------------------------------------------------
    # Interaction / alert layer
    # -----------------------------------------------------------------
    def _handle_blind_mode(self, results: List[Dict[str, Any]]) -> None:
        now = time.time()
        interval = float(self.config.get("vision", {}).get("blind_mode", {}).get("interval_seconds", 5.0))
        if now - self.last_blind_announcement < interval:
            return
        if not results:
            return

        text = self.semantic.describe(results)
        for r in results:
            name = r.get("name")
            if name and name != "Unknown":
                self.memory.set_summary(name, text)

        self._send_tts(text)
        self.last_blind_announcement = now

    def _send_tts(self, text: str) -> None:
        out_text = str(text or "")
        tcfg = self.config.get("translation", {}) if isinstance(self.config.get("translation", {}), dict) else {}
        if out_text and bool(tcfg.get("enabled", False)):
            endpoint = str(tcfg.get("endpoint", "http://localhost:8080/ollama/translate"))
            source_lang = str(tcfg.get("source_lang", "auto"))
            target_lang = str(tcfg.get("target_lang", "tr"))
            timeout = float(tcfg.get("timeout", 1.5))
            try:
                resp = requests.post(
                    endpoint,
                    params={"text": out_text, "source_lang": source_lang, "target_lang": target_lang},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("ok") and data.get("text"):
                        out_text = str(data.get("text"))
            except Exception as exc:
                logger.debug("vlm_bridge translation failed: %s", exc)

        url = self.config.get("speak", {}).get("endpoint") or "http://localhost:8083/speak/say"
        try:
            requests.post(url, json={"text": out_text}, timeout=1.0)
        except Exception as exc:
            logger.debug("Failed to send TTS: %s", exc)

    def _evaluate_alerts(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        alerts_cfg = vision_cfg.get("alerts", {})
        if not alerts_cfg or not self.mode_flags.get("hazards", True):
            return

        classes = {str(c) for c in alerts_cfg.get("classes", [])}
        dist_thr = float(alerts_cfg.get("distance_threshold_m", 1.0))
        announce_interval = float(alerts_cfg.get("announce_interval_s", 10.0))
        now = time.time()
        if now - self.last_alert_announcement < announce_interval:
            return

        hazards = []
        for r in results:
            lbl = str(r.get("label") or "")
            dist = r.get("distance_m")
            if lbl in classes and isinstance(dist, (int, float)) and float(dist) <= dist_thr:
                hazards.append((lbl, float(dist)))
        if not hazards:
            return

        parts = [f"{lbl} {dist:.1f}m" for lbl, dist in hazards]
        self._send_tts("Dikkat yakın tehlike: " + ", ".join(parts))
        self._emit_emotion("alert")
        self.last_alert_announcement = now

    def _emit_emotion(self, emotion: str) -> None:
        try:
            requests.post(
                "http://localhost:8080/interactions/event",
                json={"type": f"autonomy.{emotion}"},
                timeout=0.5,
            )
        except Exception:
            pass

    def _handle_person_interactions(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        if not self.mode_flags.get("people", True):
            return

        greet_cooldown = float(vision_cfg.get("personalization", {}).get("greet_cooldown_s", 30))
        now = time.time()
        for r in results:
            name = r.get("name")
            if not name or name == "Unknown":
                continue
            last = self._last_person_greet.get(name, 0.0)
            if now - last < greet_cooldown:
                continue

            greeting = self._build_greeting(name)
            if greeting:
                self._send_tts(greeting)
            self._emit_emotion("excited")
            self.memory.append_chat(name, role="system", text=f"Greeted: {greeting}")

            follow = self._ollama_followup(name)
            if follow:
                self._send_tts(follow)
                self.memory.append_chat(name, role="assistant", text=follow)

            self._last_person_greet[name] = now

    def _build_greeting(self, name: str) -> Optional[str]:
        p_cfg = self.config.get("vision", {}).get("personalization", {})
        known = p_cfg.get("known_people", {})
        if name in known:
            return known[name].get("greeting")
        return f"Merhaba {name}, seni gordugume sevindim."

    def _ollama_followup(self, name: str) -> Optional[str]:
        rec = self.memory.get_person(name) or {}
        last_sum = (rec.get("last_summary") or {}).get("text")
        prompt = f"{name} ile karsilastin. {('Ozet: ' + last_sum) if last_sum else ''} Turkce kisa ve sicak bir cumle soyle."
        llm_cfg = self.config.get("ollama", {}) if isinstance(self.config.get("ollama", {}), dict) else {}
        timeout = float(llm_cfg.get("timeout", 4.0))
        return generate_text(prompt, llm_cfg, timeout=timeout, response_lang="tr")
