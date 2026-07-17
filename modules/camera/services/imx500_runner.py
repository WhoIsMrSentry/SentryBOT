from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

from .onsensor_bus import OnSensorDetection, OnSensorEventBus, OnSensorSnapshot, get_default_bus
from .tracking import DetectionTracker

logger = logging.getLogger("camera.imx500_runner")

IMX500_AVAILABLE = False
IMX500_IMPORT_ERROR: Optional[str] = None

try:
    from picamera2.devices import IMX500  # type: ignore
    from picamera2.devices.imx500 import NetworkIntrinsics, postprocess_nanodet_detection  # type: ignore

    IMX500_AVAILABLE = True
except Exception as exc:
    IMX500 = None  # type: ignore
    NetworkIntrinsics = None  # type: ignore
    postprocess_nanodet_detection = None  # type: ignore
    IMX500_IMPORT_ERROR = repr(exc)


@dataclass
class Imx500Config:
    enabled: bool = True
    model_path: str = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
    labels_path: str = ""
    confidence: float = 0.50
    iou: float = 0.65
    max_detections: int = 20
    publish_interval_s: float = 0.05
    inference_rate: Optional[int] = None
    preserve_aspect_ratio: bool = True
    classes_of_interest: Sequence[str] = ()
    tracker_iou_threshold: float = 0.30
    tracker_max_missed: int = 8
    target_label: str = "person"
    target_strategy: str = "largest"


class Imx500Runner:
    def __init__(self, cfg: Imx500Config, bus: Optional[OnSensorEventBus] = None) -> None:
        self.cfg = cfg
        self.bus = bus or get_default_bus()
        self.tracker = DetectionTracker(cfg.tracker_iou_threshold, cfg.tracker_max_missed)
        self.tracker.select(cfg.target_label, cfg.target_strategy)
        self._device: Optional[Any] = None
        self._intrinsics: Optional[Any] = None
        self._picam: Optional[Any] = None
        self._metadata_source: Optional[Any] = None
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._frame_id = 0
        self._last_publish_ts = 0.0
        self._last_error = ""
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return bool(self.cfg.enabled and IMX500_AVAILABLE and os.path.exists(self.cfg.model_path))

    @property
    def running(self) -> bool:
        return bool(self._running)

    @property
    def camera_num(self) -> int:
        if self._device is None:
            return 0
        return int(getattr(self._device, "camera_num", 0))

    @property
    def inference_rate(self) -> Optional[int]:
        if self.cfg.inference_rate is not None:
            return int(self.cfg.inference_rate)
        value = getattr(self._intrinsics, "inference_rate", None)
        return int(value) if value is not None else None

    def prepare(self) -> bool:
        if not self.available:
            return False
        if self._device is not None:
            return True
        if IMX500 is None:
            return False
        self._device = IMX500(self.cfg.model_path)
        self._intrinsics = getattr(self._device, "network_intrinsics", None)
        if self._intrinsics is None and NetworkIntrinsics is not None:
            self._intrinsics = NetworkIntrinsics()
            self._intrinsics.task = "object detection"
        if self._intrinsics is not None:
            if str(getattr(self._intrinsics, "task", "object detection")) != "object detection":
                raise RuntimeError("IMX500 model is not an object detection model")
            labels = self._load_labels()
            if labels:
                self._intrinsics.labels = labels
            if self.cfg.inference_rate is not None:
                self._intrinsics.inference_rate = int(self.cfg.inference_rate)
            if hasattr(self._intrinsics, "preserve_aspect_ratio"):
                self._intrinsics.preserve_aspect_ratio = bool(self.cfg.preserve_aspect_ratio)
            if hasattr(self._intrinsics, "update_with_defaults"):
                self._intrinsics.update_with_defaults()
        if bool(self.cfg.preserve_aspect_ratio) and hasattr(self._device, "set_auto_aspect_ratio"):
            self._device.set_auto_aspect_ratio()
        if hasattr(self._device, "show_network_fw_progress_bar"):
            self._device.show_network_fw_progress_bar()
        return True

    def attach_camera(self, picam: Any, metadata_source: Optional[Any] = None) -> None:
        self._picam = picam
        self._metadata_source = metadata_source

    def start(self) -> bool:
        if self.running:
            return True
        if not self.prepare() or self._picam is None:
            return False
        self._stop.clear()
        if self._metadata_source is not None and hasattr(self._metadata_source, "subscribe_metadata"):
            self._unsubscribe = self._metadata_source.subscribe_metadata(self._on_metadata)
            self._running = True
            return True
        self._thread = threading.Thread(target=self._metadata_loop, name="imx500-inference", daemon=True)
        self._thread.start()
        self._running = True
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
        self._unsubscribe = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._running = False

    def select_target(self, label: str = "person", strategy: str = "largest", track_id: Optional[int] = None) -> dict[str, Any]:
        return self.tracker.select(label, strategy, track_id)

    def target(self) -> dict[str, Any]:
        target = self.tracker.target()
        return {"ok": target is not None, "selection": self.tracker.selection(), "target": target.to_dict() if target else None}

    def tracks(self) -> dict[str, Any]:
        tracks = self.tracker.tracks()
        return {"ok": True, "count": len(tracks), "tracks": tracks, "selection": self.tracker.selection()}

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.cfg.enabled),
            "available": self.available,
            "running": self.running,
            "reason": self._status_reason(),
            "model_path": self.cfg.model_path,
            "model_exists": os.path.exists(self.cfg.model_path),
            "confidence": self.cfg.confidence,
            "inference_rate": self.inference_rate,
            "camera_num": self.camera_num,
            "frame_id": self._frame_id,
            "last_publish_age_s": max(0.0, time.time() - self._last_publish_ts) if self._last_publish_ts else None,
            "last_error": self._last_error,
            "import_error": IMX500_IMPORT_ERROR,
            "tracking": self.target(),
        }

    def _status_reason(self) -> str:
        if not self.cfg.enabled:
            return "disabled"
        if not IMX500_AVAILABLE:
            return "library_unavailable"
        if not os.path.exists(self.cfg.model_path):
            return "model_missing"
        if self.running:
            return "running"
        if self._picam is None:
            return "camera_not_attached"
        return "ready"

    def _load_labels(self) -> List[str]:
        if self.cfg.labels_path and os.path.exists(self.cfg.labels_path):
            with open(self.cfg.labels_path, "r", encoding="utf-8") as handle:
                return [line.strip() for line in handle if line.strip()]
        labels = getattr(self._intrinsics, "labels", None)
        return [str(label) for label in labels] if labels else []

    def _label_for(self, class_id: int) -> str:
        labels = getattr(self._intrinsics, "labels", None) or []
        if bool(getattr(self._intrinsics, "ignore_dash_labels", False)):
            labels = [label for label in labels if label and label != "-"]
        if 0 <= class_id < len(labels):
            return str(labels[class_id])
        return f"class_{class_id}"

    def _metadata_loop(self) -> None:
        while not self._stop.is_set():
            try:
                metadata = self._picam.capture_metadata()
                self._on_metadata(dict(metadata or {}))
            except Exception as exc:
                self._last_error = str(exc)
                logger.debug("IMX500 metadata capture failed: %s", exc)
            time.sleep(0.01)

    def _on_metadata(self, metadata: dict[str, Any]) -> None:
        now = time.time()
        if now - self._last_publish_ts < max(0.01, float(self.cfg.publish_interval_s)):
            return
        try:
            snapshot = self._parse(metadata)
            if snapshot is not None:
                self.bus.publish(snapshot)
                self._last_publish_ts = now
                self._last_error = ""
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("IMX500 inference failed: %s", exc)

    def _parse(self, metadata: dict[str, Any]) -> Optional[OnSensorSnapshot]:
        if self._device is None:
            return None
        outputs = self._device.get_outputs(metadata, add_batch=True)
        if outputs is None:
            return None
        boxes, scores, classes = self._unpack(outputs)
        detections: List[OnSensorDetection] = []
        width, height = self._frame_size()
        wanted = {str(label).strip().lower() for label in self.cfg.classes_of_interest if str(label).strip()}
        for box, score, class_id in zip(boxes, scores, classes):
            score_value = float(score)
            if score_value < float(self.cfg.confidence):
                continue
            label = self._label_for(int(class_id))
            if wanted and label.lower() not in wanted:
                continue
            detections.append(
                OnSensorDetection(
                    class_id=int(class_id),
                    label=label,
                    score=score_value,
                    bbox_xyxy_norm=self._normalise_box(box, metadata, width, height),
                )
            )
        tracked = self.tracker.update(detections)
        target = self.tracker.target()
        self._frame_id += 1
        return OnSensorSnapshot(
            ts=time.time(),
            frame_id=self._frame_id,
            width=width,
            height=height,
            detections=tracked,
            backend="imx500",
            target_track_id=target.track_id if target else None,
            target_label=target.label if target else "",
        )

    def _unpack(self, outputs: Any) -> Tuple[Any, Any, Any]:
        if str(getattr(self._intrinsics, "postprocess", "")) == "nanodet" and postprocess_nanodet_detection is not None:
            boxes, scores, classes = postprocess_nanodet_detection(
                outputs=outputs[0],
                conf=float(self.cfg.confidence),
                iou_thres=float(self.cfg.iou),
                max_out_dets=int(self.cfg.max_detections),
            )[0]
            try:
                from picamera2.devices.imx500.postprocess import scale_boxes  # type: ignore

                input_w, input_h = self._device.get_input_size()
                boxes = scale_boxes(boxes, 1, 1, input_h, input_w, False, False)
            except Exception:
                pass
            return boxes, scores, classes
        return outputs[0][0], outputs[1][0], outputs[2][0]

    def _normalise_box(self, box: Any, metadata: dict[str, Any], width: int, height: int) -> Tuple[float, float, float, float]:
        values = [float(value) for value in box]
        if bool(getattr(self._intrinsics, "bbox_normalization", False)):
            _, input_h = self._device.get_input_size()
            values = [value / float(input_h) for value in values]
        if str(getattr(self._intrinsics, "bbox_order", "yx")) == "xy":
            values = [values[1], values[0], values[3], values[2]]
        if hasattr(self._device, "convert_inference_coords") and self._picam is not None:
            x, y, box_width, box_height = self._device.convert_inference_coords(values, metadata, self._picam)
            return self._clamp_box((x / width, y / height, (x + box_width) / width, (y + box_height) / height))
        y1, x1, y2, x2 = values
        return self._clamp_box((x1, y1, x2, y2))

    def _frame_size(self) -> Tuple[int, int]:
        try:
            size = self._picam.camera_config["main"]["size"]
            return int(size[0]), int(size[1])
        except Exception:
            return 1280, 720

    @staticmethod
    def _clamp_box(box: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        return tuple(max(0.0, min(1.0, float(value))) for value in box)  # type: ignore[return-value]


__all__ = ["Imx500Config", "Imx500Runner", "IMX500_AVAILABLE", "IMX500_IMPORT_ERROR"]
