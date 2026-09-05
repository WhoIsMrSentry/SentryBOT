from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

import requests

logger = logging.getLogger("vlm_bridge")


class ProcessorStreamMixin:
    """Camera capture loops, inference stream, and frame generation for VisionProcessor."""

    processing_mode: str
    hybrid_local_capture: bool
    _camera_hardware_available: bool
    camera_source: Any
    _max_camera_wait_attempts: int
    _camera_gave_up: bool
    _stop_event: threading.Event
    _capture_thread: Optional[threading.Thread]
    _inference_thread: Optional[threading.Thread]
    _frame_lock: threading.Lock
    _latest_raw_frame: Optional[Any]
    _latest_annotated_frame: Optional[bytes]
    latest_results: List[Dict[str, Any]]
    blind_mode_enabled: bool
    mode_flags: Dict[str, bool]
    action_dispatcher: Any
    semantic: Any
    _follow_active: bool

    def start_stream_processing(self) -> None:
        if not self._needs_local_capture():
            logger.debug("start_stream_processing() ignored in remote-only mode")
            return
        if not self._camera_hardware_available:
            logger.info("start_stream_processing skipped: camera hardware not available")
            return
        self._camera_gave_up = False
        if self._capture_thread and self._capture_thread.is_alive():
            return

        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        if self.processing_mode == "local":
            self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
            self._inference_thread.start()
            logger.info("Vision processing started (OpenCV face mode)")
        else:
            self._inference_thread = threading.Thread(target=self._hybrid_vlm_loop, daemon=True)
            self._inference_thread.start()
            logger.info("Vision hybrid capture started (remote infer + local frames)")

    def _hybrid_vlm_loop(self) -> None:
        interval = max(4.0, float(getattr(getattr(self, "vision_sampler", None), "min_interval_s", 5.0)))
        while not self._stop_event.is_set():
            try:
                self._maybe_sample_vlm(list(self.latest_results))
            except Exception:
                pass
            time.sleep(interval)

    def stop_stream_processing(self) -> None:
        if self.processing_mode != "local" and not self.hybrid_local_capture:
            return
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._inference_thread:
            self._inference_thread.join(timeout=2.0)
        logger.info("Vision processing stopped")

    def _is_http_camera_source(self) -> bool:
        src = self.camera_source
        return isinstance(src, str) and src.lower().startswith(("http://", "https://"))

    def _camera_probe_url(self) -> Optional[str]:
        if not self._is_http_camera_source():
            return None
        src = str(self.camera_source)
        if "/camera/video" in src:
            return src.replace("/camera/video", "/camera/healthz")
        return src

    def _http_camera_ready(self) -> bool:
        probe = self._camera_probe_url()
        if not probe:
            return True
        try:
            resp = requests.get(probe, timeout=1.0)
            return resp.status_code == 200
        except Exception:
            return False

    def _capture_loop(self) -> None:
        cap: Optional[Any] = None
        open_fail_count = 0

        while not self._stop_event.is_set():
            if cap is None or not cap.isOpened():
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

                if self._is_http_camera_source() and not self._http_camera_ready():
                    open_fail_count += 1
                    if open_fail_count % 10 == 1:
                        logger.info("Camera source not ready yet: %s, waiting...", self.camera_source)
                    time.sleep(1.0)
                    continue

                if cv2 is not None:
                    cap = cv2.VideoCapture(self.camera_source)
                if cap is None or not cap.isOpened():
                    open_fail_count += 1
                    if open_fail_count >= self._max_camera_wait_attempts:
                        if not self._camera_gave_up:
                            self._camera_gave_up = True
                            logger.warning(
                                "Could not open camera source after %d attempts: %s; pausing retries",
                                self._max_camera_wait_attempts,
                                self.camera_source,
                            )
                        time.sleep(3.0)
                        open_fail_count = 0
                        continue
                    if open_fail_count == 1 or open_fail_count == self._max_camera_wait_attempts:
                        logger.warning(
                            "Could not open camera source: %s (attempt=%d/%d), retrying...",
                            self.camera_source,
                            open_fail_count,
                            self._max_camera_wait_attempts,
                        )
                    time.sleep(1.0)
                    continue

                open_fail_count = 0
                logger.info("Camera source connected: %s", self.camera_source)

            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Failed to read frame, reconnecting camera source...")
                time.sleep(0.6)
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                continue

            with self._frame_lock:
                self._latest_raw_frame = frame

            time.sleep(0.003)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

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
            if self._onsensor_active():
                extras = self._onsensor_object_results()
                if extras:
                    parsed_results = list(parsed_results) + extras
            self.latest_results = parsed_results

            self._maybe_sample_vlm(parsed_results)

            self._handle_person_interactions(parsed_results)
            if not self._follow_active:
                self._evaluate_alerts(parsed_results)
                if parsed_results and self.mode_flags.get("semantic_scene", True):
                    self.action_dispatcher.emit_scene(self.semantic, parsed_results)
                if self.blind_mode_enabled and parsed_results:
                    self._handle_blind_mode(parsed_results)

            if cv2 is not None:
                ok, buf = cv2.imencode(".jpg", annotated)
                if ok:
                    with self._frame_lock:
                        self._latest_annotated_frame = buf.tobytes()

            time.sleep(0.05)

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

        if self._is_http_camera_source():
            frame = None
            with self._frame_lock:
                if self._latest_raw_frame is not None:
                    frame = self._latest_raw_frame.copy()
            if frame is None:
                return [{"error": "No frame available yet"}]
            results, _annotated = self._analyze_frame(frame, enable_follow=False)
            return results

        if cv2 is None:
            return [{"error": "OpenCV not available"}]
        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            return [{"error": "Could not open camera"}]
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return [{"error": "Failed to capture frame"}]

        results, _annotated = self._analyze_frame(frame, enable_follow=False)
        return results

    def _grab_frame(self) -> Optional[Any]:
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                return self._latest_raw_frame.copy()
        if self._is_http_camera_source():
            return None
        if cv2 is None:
            return None
        try:
            cap = cv2.VideoCapture(self.camera_source)
            if cap.isOpened():
                ok, snap = cap.read()
                cap.release()
                if ok and snap is not None:
                    return snap
        except Exception:
            pass
        return None

    def _encode_frame_b64(self, frame: Any, quality: int = 80) -> Optional[str]:
        if cv2 is None:
            return None
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
            if not ok:
                return None
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:
            return None
