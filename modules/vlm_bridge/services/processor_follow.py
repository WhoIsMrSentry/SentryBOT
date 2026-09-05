from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore
import requests

_FOLLOW_LOCK_INIT_LOCK = threading.Lock()

try:
    from .head_control_arbiter import HeadCommand
except Exception:
    HeadCommand = None  # type: ignore

try:
    from .vision_event_bus import (
        EVENT_FOLLOW_START,
        EVENT_FOLLOW_STOP,
    )
except Exception:
    EVENT_FOLLOW_START = "follow_start"
    EVENT_FOLLOW_STOP = "follow_stop"

logger = logging.getLogger("vlm_bridge.follow")


def _create_csrt_tracker() -> Optional[Any]:
    try:
        from . import processor
        active_cv2 = getattr(processor, "cv2", cv2)
    except Exception:
        active_cv2 = cv2
    if active_cv2 is None:
        return None
    if hasattr(active_cv2, "TrackerCSRT_create"):
        try:
            return active_cv2.TrackerCSRT_create()
        except Exception:
            pass
    legacy = getattr(active_cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        try:
            return legacy.TrackerCSRT_create()
        except Exception:
            pass
    return None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class ProcessorFollowMixin:
    """Follow and CSRT tracking logic for VisionProcessor."""

    _follow_cfg: Dict[str, Any]
    _follow_active: bool
    _follow_target: Optional[str]
    _follow_tracker: Optional[Any]
    _follow_lost_frames: int
    _follow_last_track_ts: float
    _follow_current_bbox: Optional[Tuple[int, int, int, int]]
    _track_callback: Optional[Callable[..., Any]]
    processing_mode: str
    _camera_hardware_available: bool
    event_bus: Optional[Any]
    head_arbiter: Optional[Any]
    _gateway_base: str

    def _follow_lock_obj(self):
        # Race-free lazy init (R8): two threads must never create separate
        # locks, or mutual exclusion silently disappears.
        lock = getattr(self, "_follow_lock", None)
        if lock is None:
            with _FOLLOW_LOCK_INIT_LOCK:
                lock = getattr(self, "_follow_lock", None)
                if lock is None:
                    lock = threading.RLock()
                    self._follow_lock = lock
        return lock

    def set_track_callback(self, callback: Callable[..., Any]) -> None:
        self._track_callback = callback

    def start_follow(self, person: Optional[str] = None) -> Dict[str, Any]:
        if not self._follow_cfg.get("enabled", True):
            return {"ok": False, "error": "follow mode disabled"}

        with self._follow_lock_obj():
            self._follow_active = True
            self._follow_target = str(person).strip() if person else None
            self._follow_tracker = None
            self._follow_lost_frames = 0
            self._follow_current_bbox = None
            target = self._follow_target

        if self.processing_mode == "local":
            if not self._camera_hardware_available:
                with self._follow_lock_obj():
                    self._follow_active = False
                    self._follow_target = None
                    self._follow_tracker = None
                    self._follow_lost_frames = 0
                    self._follow_current_bbox = None
                return {"ok": False, "error": "camera_disabled"}
            if hasattr(self, "start_stream_processing"):
                self.start_stream_processing()

        if self.event_bus is not None:
            self.event_bus.publish(EVENT_FOLLOW_START, {"target": target})

        status = self.follow_status()
        status["ok"] = True
        return status

    def stop_follow(self) -> Dict[str, Any]:
        with self._follow_lock_obj():
            self._follow_active = False
            self._follow_target = None
            self._follow_tracker = None
            self._follow_lost_frames = 0
            self._follow_current_bbox = None
        if self.event_bus is not None:
            self.event_bus.publish(EVENT_FOLLOW_STOP, {})
        return {"ok": True, **self.follow_status()}

    def follow_status(self) -> Dict[str, Any]:
        with self._follow_lock_obj():
            return {
                "active": bool(self._follow_active),
                "target": self._follow_target,
                "tracking": bool(self._follow_tracker is not None),
                "bbox": list(self._follow_current_bbox) if self._follow_current_bbox else None,
                "mode": self.processing_mode,
            }

    def _update_tracker(self, frame: Any) -> Optional[Tuple[int, int, int, int]]:
        with self._follow_lock_obj():
            if not self._follow_active:
                return None
            if getattr(self, "_onsensor_active", lambda: False)():
                snap = getattr(self, "_latest_onsensor_snapshot", lambda: None)()
                if snap is not None and getattr(snap, "target_track_id", None) is not None:
                    for det in getattr(snap, "detections", []):
                        if getattr(det, "track_id", None) == snap.target_track_id:
                            bbox = getattr(det, "bbox_xyxy_norm", None)
                            if bbox and len(bbox) == 4:
                                h, w = frame.shape[:2]
                                x1n, y1n, x2n, y2n = [float(v) for v in bbox]
                                if max(x2n, y2n) <= 1.5:
                                    x1, y1 = int(_clamp(int(x1n * w), 0, w - 1)), int(_clamp(int(y1n * h), 0, h - 1))
                                    x2, y2 = int(_clamp(int(x2n * w), 0, w)), int(_clamp(int(y2n * h), 0, h))
                                else:
                                    x1, y1 = int(_clamp(int(x1n), 0, w - 1)), int(_clamp(int(y1n), 0, h - 1))
                                    x2, y2 = int(_clamp(int(x2n), 0, w)), int(_clamp(int(y2n), 0, h))
                                if x2 > x1 and y2 > y1:
                                    self._follow_current_bbox = (x1, y1, x2, y2)
                                    self._follow_lost_frames = 0
                                    return self._follow_current_bbox
                self._follow_lost_frames += 1
                if self._follow_lost_frames >= int(self._follow_cfg.get("max_lost_frames", 18)):
                    self._follow_current_bbox = None
                return None

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
        with self._follow_lock_obj():
            if not self._follow_active:
                return None
            if getattr(self, "_onsensor_active", lambda: False)():
                self._follow_tracker = None
                return

            if not results:
                return

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
        with self._follow_lock_obj():
            if not self._follow_active or not results:
                return

            now = time.time()
            if now - self._follow_last_track_ts < float(self._follow_cfg.get("track_interval_s", 0.12)):
                return

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

            dx_norm = (cx - (w * 0.5)) / max(1.0, w * 0.5)
            dy_norm = (cy - (h * 0.5)) / max(1.0, h * 0.5)

            pan = int(
                round(
                    float(self._follow_cfg.get("center_pan", 90))
                    + dx_norm * float(self._follow_cfg.get("pan_gain_deg", 50.0))
                )
            )
            tilt = int(
                round(
                    float(self._follow_cfg.get("center_tilt", 90))
                    + dy_norm * float(self._follow_cfg.get("tilt_gain_deg", 32.0))
                )
            )

            pan = _clamp(
                pan,
                int(self._follow_cfg.get("min_pan", 35)),
                int(self._follow_cfg.get("max_pan", 145)),
            )
            tilt = _clamp(
                tilt,
                int(self._follow_cfg.get("min_tilt", 65)),
                int(self._follow_cfg.get("max_tilt", 125)),
            )

            target_name = str(self._follow_target or "").lower()
            self._follow_last_track_ts = now

        if self.head_arbiter is not None and HeadCommand is not None:
            source = "owner_follow" if target_name in {"owner", "emir"} else "active_speaker"
            priority = 85 if source == "owner_follow" else 75
            self.head_arbiter.request_move(
                HeadCommand(pan=float(pan), tilt=float(tilt), source=source, priority=priority, ttl_s=1.0)
            )
        else:
            self._send_track(pan=pan, tilt=tilt, drive=0)

    def _send_track(self, pan: int, tilt: int, drive: int = 0) -> None:
        if self._track_callback is not None:
            try:
                self._track_callback(head_pan=float(pan), head_tilt=float(tilt), drive=int(drive))
                return
            except Exception as exc:
                logger.debug("track callback failed: %s", exc)

        try:
            from modules.gateway.url import gateway_url

            requests.post(
                gateway_url(self._gateway_base, "/vlm/track"),
                params={"head_pan": float(pan), "head_tilt": float(tilt), "drive": int(drive)},
                timeout=0.25,
            )
        except Exception:
            pass
