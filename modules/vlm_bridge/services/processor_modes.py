from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("vlm_bridge")


class ProcessorModesMixin:
    """Mode configurations, profiles, and runtime capabilities for VisionProcessor."""

    config: Dict[str, Any]
    processing_mode: str
    hybrid_local_capture: bool
    _camera_hardware_available: bool
    _camera_gave_up: bool
    mode_flags: Dict[str, bool]
    mode_categories: Dict[str, Dict[str, bool]]
    mode_profiles: Dict[str, Dict[str, bool]]
    _active_realtime_profile: str
    _realtime_profiles: Dict[str, Dict[str, Any]]
    _follow_cfg: Dict[str, Any]
    vlm_client: Any
    _frame_lock: Any
    _latest_raw_frame: Any
    _capture_thread: Any
    latest_results: List[Dict[str, Any]]

    @staticmethod
    def _init_mode_flags(vision_cfg: dict) -> Dict[str, bool]:
        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes"), dict) else {}
        return {
            "objects": bool(raw_modes.get("objects", True)),
            "people": bool(raw_modes.get("people", True)),
            "faces": bool(raw_modes.get("faces", True)),
            "depth": bool(raw_modes.get("depth", False)),
            "ocr": bool(raw_modes.get("ocr", False)),
            "hazards": bool(raw_modes.get("hazards", True)),
            "semantic_scene": bool(raw_modes.get("semantic_scene", True)),
        }

    @staticmethod
    def _init_mode_categories(vision_cfg: dict, mode_flags: dict) -> Dict[str, Dict[str, bool]]:
        raw_categories = (
            vision_cfg.get("mode_categories", {}) if isinstance(vision_cfg.get("mode_categories"), dict) else {}
        )

        def _bool_map(section: Dict[str, Any]) -> Dict[str, bool]:
            return {str(k): bool(v) for k, v in (section or {}).items()}

        return {
            "local": _bool_map(raw_categories.get("local", {"face_match": True, "visual_logger": True})),
            "remote": _bool_map(
                raw_categories.get(
                    "remote",
                    {
                        "objects": mode_flags["objects"],
                        "people": mode_flags["people"],
                        "faces": mode_flags["faces"],
                        "ocr": mode_flags["ocr"],
                        "hazards": mode_flags["hazards"],
                        "semantic_scene": mode_flags["semantic_scene"],
                        "depth": mode_flags["depth"],
                    },
                )
            ),
            "onsensor": _bool_map(raw_categories.get("onsensor", {"tiny_detect": False, "tiny_pose": False})),
        }

    def _apply_aliases_and_disabled(self, vision_cfg: dict) -> None:
        for alias_key in ("local_modes", "remote_modes", "onsensor_modes"):
            bucket_key = alias_key.replace("_modes", "")
            if bucket_key not in self.mode_categories:
                continue
            raw = vision_cfg.get(alias_key) or (
                vision_cfg.get("sensor_modes") if alias_key == "onsensor_modes" else None
            )
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in self.mode_categories[bucket_key]:
                        self.mode_categories[bucket_key][key] = bool(value)
        disabled = vision_cfg.get("disabled_modes") or {}
        if isinstance(disabled, dict):
            for key, value in disabled.items():
                if not bool(value):
                    continue
                for bucket in self.mode_categories.values():
                    if key in bucket:
                        bucket[key] = False
                if key in self.mode_flags:
                    self.mode_flags[key] = False

    @staticmethod
    def _init_mode_profiles(vision_cfg: dict, mode_flags: dict = None) -> Dict[str, Dict[str, bool]]:
        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes"), dict) else {}
        return {
            "balanced": dict(mode_flags) if mode_flags else {},
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

    def get_modes(self) -> Dict[str, bool]:
        return dict(self.mode_flags)

    def get_mode_categories(self) -> Dict[str, Dict[str, bool]]:
        return {
            "local": dict(self.mode_categories.get("local", {})),
            "remote": dict(self.mode_categories.get("remote", {})),
            "onsensor": dict(self.mode_categories.get("onsensor", {})),
        }

    def set_mode_categories(self, updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        changed: Dict[str, Dict[str, bool]] = {}
        for category, payload in (updates or {}).items():
            if category not in self.mode_categories or not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if key in self.mode_categories[category]:
                    self.mode_categories[category][key] = bool(value)
                    changed.setdefault(category, {})[key] = self.mode_categories[category][key]
        return {"ok": True, "changed": changed, "mode_categories": self.get_mode_categories()}

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

        if not self._camera_hardware_available:
            return {
                "ok": False,
                "error": "camera_disabled",
                "processing_mode": self.processing_mode,
            }

        self.processing_mode = "local"
        self._ensure_face_manager()
        self.start_stream_processing()
        return {"ok": True, "processing_mode": self.processing_mode}

    def get_realtime_profile_status(self) -> Dict[str, Any]:
        active = self._active_realtime_profile
        return {
            "ok": True,
            "active": active,
            "profiles": sorted(self._realtime_profiles.keys()),
            "settings": dict(self._realtime_profiles.get(active, {})),
        }

    def apply_realtime_profile(self, mode: str) -> Dict[str, Any]:
        key = str(mode or "").strip().lower()
        profile = self._realtime_profiles.get(key)
        if not profile:
            return {
                "ok": False,
                "error": "unknown_profile",
                "profiles": sorted(self._realtime_profiles.keys()),
            }

        self._active_realtime_profile = key
        applied: Dict[str, Any] = {}

        if self.vlm_client is not None:
            if "vlm_timeout_s" in profile:
                self.vlm_client.timeout = float(profile["vlm_timeout_s"])
                applied["vlm_timeout_s"] = self.vlm_client.timeout
            if "vlm_min_interval_s" in profile:
                self.vlm_client.min_interval_s = float(profile["vlm_min_interval_s"])
                applied["vlm_min_interval_s"] = self.vlm_client.min_interval_s
            if "vlm_num_predict" in profile and hasattr(self.vlm_client, "num_predict"):
                self.vlm_client.num_predict = int(profile["vlm_num_predict"])
                applied["vlm_num_predict"] = self.vlm_client.num_predict

        if "follow_track_interval_s" in profile:
            self._follow_cfg["track_interval_s"] = float(profile["follow_track_interval_s"])
            applied["follow_track_interval_s"] = self._follow_cfg["track_interval_s"]

        return {"ok": True, "active": key, "applied": applied}

    def set_camera_hardware_available(self, available: bool) -> None:
        self._camera_hardware_available = bool(available)
        if not self._camera_hardware_available:
            self._camera_gave_up = False

    def _needs_local_capture(self) -> bool:
        hybrid = self.hybrid_local_capture and self.processing_mode == "remote"
        return self.processing_mode == "local" or hybrid

    def has_vision_context(self) -> bool:
        try:
            ctx = self.get_latest_visual_context()
            if ctx is not None:
                return True
        except Exception:
            pass
        return bool(self.latest_results)

    def is_local_camera_available(self) -> bool:
        if not self._camera_hardware_available:
            return False
        if not self._needs_local_capture():
            return False
        if self._is_http_camera_source():
            ready = self._http_camera_ready()
            if ready and self._camera_gave_up:
                self._camera_gave_up = False
            return ready and not self._camera_gave_up
        if self._camera_gave_up:
            return False
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                return True
        thread = self._capture_thread
        return thread is not None and thread.is_alive()

    def is_camera_input_available(self) -> bool:
        return self.is_local_camera_available()

    def locate_object(self, query: str, orient_head: bool = True) -> Dict[str, Any]:
        """Locate an object or person in the current visual cache/results and optionally orient head."""
        q = str(query or "").strip().lower()
        if not q:
            return {"ok": False, "found": False, "error": "empty_query"}

        candidates: List[Dict[str, Any]] = []

        # 1. Inspect VisualContextCache (if available)
        cache = getattr(self, "visual_context_cache", None) or getattr(self, "context_cache", None)
        if cache is not None and hasattr(cache, "get_latest"):
            try:
                latest_ctx = cache.get_latest()
                if latest_ctx is not None:
                    for obj in getattr(latest_ctx, "objects", []) or []:
                        if isinstance(obj, dict):
                            candidates.append(dict(obj))
                    for person in getattr(latest_ctx, "people", []) or []:
                        p_dict = person.to_dict() if hasattr(person, "to_dict") else (dict(person) if isinstance(person, dict) else {})
                        if p_dict:
                            p_dict.setdefault("label", "person")
                            candidates.append(p_dict)
            except Exception:
                pass

        # 2. Inspect latest_results / last_result
        for r in getattr(self, "latest_results", None) or getattr(self, "last_result", None) or []:
            if isinstance(r, dict):
                candidates.append(dict(r))

        matched: Dict[str, Any] | None = None
        best_conf = -1.0
        for item in candidates:
            label = str(item.get("label") or "").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            if q in label or q in name or (label and label in q) or (name and name != "unknown" and name in q):
                conf = float(item.get("confidence", item.get("conf", 0.5)) or 0.5)
                if conf > best_conf:
                    best_conf = conf
                    matched = item

        if matched is None:
            return {"ok": True, "found": False, "query": query}

        # Normalize bbox to [ymin, xmin, ymax, xmax] in 0.0..1.0
        raw_bbox = matched.get("bbox_norm") or matched.get("bbox") or matched.get("box") or [0.25, 0.25, 0.75, 0.75]
        frame_w, frame_h = 640.0, 480.0
        raw_frame = getattr(self, "_latest_raw_frame", None)
        if raw_frame is not None and hasattr(raw_frame, "shape") and len(raw_frame.shape) >= 2:
            frame_h = float(raw_frame.shape[0] or 480.0)
            frame_w = float(raw_frame.shape[1] or 640.0)

        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
            b0, b1, b2, b3 = [float(v) for v in raw_bbox[:4]]
            if max(abs(b0), abs(b1), abs(b2), abs(b3)) > 1.5:
                # Assume pixel [x1, y1, x2, y2]
                xmin = max(0.0, min(1.0, b0 / frame_w))
                ymin = max(0.0, min(1.0, b1 / frame_h))
                xmax = max(0.0, min(1.0, b2 / frame_w))
                ymax = max(0.0, min(1.0, b3 / frame_h))
            else:
                # Already normalized: check if [x1, y1, x2, y2] or [ymin, xmin, ymax, xmax]
                if "bbox_ymin_xmin_ymax_xmax" in matched:
                    ymin, xmin, ymax, xmax = [max(0.0, min(1.0, float(v))) for v in matched["bbox_ymin_xmin_ymax_xmax"][:4]]
                else:
                    ymin = max(0.0, min(1.0, b1))
                    xmin = max(0.0, min(1.0, b0))
                    ymax = max(0.0, min(1.0, b3))
                    xmax = max(0.0, min(1.0, b2))
        else:
            ymin, xmin, ymax, xmax = 0.25, 0.25, 0.75, 0.75

        norm_bbox = [round(ymin, 4), round(xmin, 4), round(ymax, 4), round(xmax, 4)]
        cx = (xmin + xmax) * 0.5
        cy = (ymin + ymax) * 0.5

        follow_cfg = getattr(self, "_follow_cfg", {}) or {}
        pan_gain = float(follow_cfg.get("pan_gain_deg", 50.0))
        tilt_gain = float(follow_cfg.get("tilt_gain_deg", 32.0))
        center_pan = float(follow_cfg.get("center_pan", 90.0))
        center_tilt = float(follow_cfg.get("center_tilt", 90.0))

        pan_delta_deg = round((0.5 - cx) * pan_gain, 2)
        tilt_delta_deg = round((0.5 - cy) * tilt_gain, 2)
        target_pan = round(center_pan + pan_delta_deg, 1)
        target_tilt = round(center_tilt + tilt_delta_deg, 1)

        head_move_result = None
        arbiter = getattr(self, "head_arbiter", None)
        if orient_head and arbiter is not None and hasattr(arbiter, "move"):
            try:
                pos = getattr(arbiter, "current_position", None)
                if isinstance(pos, dict):
                    target_pan = round(float(pos.get("pan", center_pan)) + pan_delta_deg, 1)
                    target_tilt = round(float(pos.get("tilt", center_tilt)) + tilt_delta_deg, 1)
                head_move_result = arbiter.move(
                    pan=target_pan,
                    tilt=target_tilt,
                    source="vlm_interest",
                    priority=50,
                )
            except Exception as exc:
                head_move_result = {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "found": True,
            "query": query,
            "label": matched.get("label") or matched.get("name") or query,
            "name": matched.get("name", "Unknown"),
            "confidence": round(max(0.0, best_conf), 4),
            "bbox": norm_bbox,
            "center": [round(cy, 4), round(cx, 4)],
            "pan_delta_deg": pan_delta_deg,
            "tilt_delta_deg": tilt_delta_deg,
            "target_pan": target_pan,
            "target_tilt": target_tilt,
            "head_move": head_move_result,
        }

