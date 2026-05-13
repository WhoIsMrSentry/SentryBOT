"""Sony IMX500 (Raspberry Pi AI Camera) on-sensor inference runner.

This module wires the on-sensor SSD MobileNet network (or any user provided
``.rpk`` model) into the SentryBOT pipeline. The runner stays *inert* when the
optional ``picamera2`` package or the IMX500 device is not available, so it can
be safely imported on developer machines without breaking startup.

Whenever the IMX500 emits detections, the runner translates them into
:class:`OnSensorSnapshot` objects and forwards them through the shared
:class:`OnSensorEventBus`. The VLM bridge processor subscribes to the bus and
can therefore replace its Haar face detector with the IMX500 results when the
backend is active.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from .onsensor_bus import OnSensorDetection, OnSensorEventBus, OnSensorSnapshot, get_default_bus

logger = logging.getLogger("camera.imx500_runner")


IMX500_AVAILABLE = False
IMX500_IMPORT_ERROR: Optional[str] = None

try:
    from picamera2 import Picamera2  # type: ignore  # noqa: F401
    from picamera2.devices.imx500 import IMX500, NetworkIntrinsics  # type: ignore
    IMX500_AVAILABLE = True
except Exception as exc:  # pragma: no cover - device specific path
    IMX500 = None  # type: ignore
    NetworkIntrinsics = None  # type: ignore
    IMX500_IMPORT_ERROR = repr(exc)


@dataclass
class Imx500Config:
    enabled: bool = False
    model_path: str = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"
    labels_path: str = "/usr/share/imx500-models/coco_labels.txt"
    confidence: float = 0.45
    publish_metadata: bool = True
    publish_interval_s: float = 0.05
    classes_of_interest: Sequence[str] = ()


class Imx500Runner:
    """Manages the IMX500 inference loop and publishes detections to the bus."""

    def __init__(
        self,
        cfg: Imx500Config,
        bus: Optional[OnSensorEventBus] = None,
        picam: Optional[Any] = None,
    ) -> None:
        self.cfg = cfg
        self.bus = bus or get_default_bus()
        self._picam = picam
        self._device: Optional[Any] = None
        self._intrinsics: Optional[Any] = None
        self._labels: List[str] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_id = 0
        self._last_publish_ts = 0.0
        self._available = bool(cfg.enabled) and IMX500_AVAILABLE

        if cfg.enabled and not IMX500_AVAILABLE:
            logger.info(
                "IMX500 requested but picamera2/IMX500 unavailable (%s); runner stays inert.",
                IMX500_IMPORT_ERROR,
            )

    # -- Public lifecycle ------------------------------------------------

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> bool:
        """Initialise the device and start the background loop.

        Returns ``True`` when the runner is actually running, ``False`` when it
        is skipped (disabled or library missing).
        """
        if not self._available:
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            self._init_device()
        except Exception as exc:  # pragma: no cover - hardware specific
            logger.warning("IMX500 init failed (%s); runner disabled.", exc)
            self._available = False
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="imx500-runner", daemon=True)
        self._thread.start()
        logger.info("IMX500 runner started (model=%s).", self.cfg.model_path)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    # -- Internals -------------------------------------------------------

    def _init_device(self) -> None:
        if IMX500 is None:  # pragma: no cover
            raise RuntimeError("IMX500 library not loaded")
        model_path = self.cfg.model_path
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"IMX500 model_path not found: {model_path}")

        self._device = IMX500(model_path)
        try:
            self._intrinsics = self._device.network_intrinsics
        except Exception:
            self._intrinsics = None

        labels_path = self.cfg.labels_path
        if labels_path and os.path.exists(labels_path):
            try:
                with open(labels_path, "r", encoding="utf-8") as fh:
                    self._labels = [line.strip() for line in fh.readlines() if line.strip()]
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Failed to read IMX500 labels file: %s", exc)

    def _label_for(self, class_id: int) -> str:
        if 0 <= class_id < len(self._labels):
            return self._labels[class_id]
        return f"class_{class_id}"

    def _should_emit(self, label: str) -> bool:
        wanted = set(s.strip().lower() for s in self.cfg.classes_of_interest or [])
        if not wanted:
            return True
        return label.strip().lower() in wanted

    def _loop(self) -> None:
        device = self._device
        if device is None:
            return
        interval = max(0.0, float(self.cfg.publish_interval_s or 0.05))
        while not self._stop.is_set():
            try:
                snapshot = self._fetch_snapshot()
            except Exception as exc:
                logger.debug("IMX500 fetch failed: %s", exc)
                snapshot = None
            if snapshot is not None:
                now = time.time()
                if (now - self._last_publish_ts) >= interval:
                    self.bus.publish(snapshot)
                    self._last_publish_ts = now
            time.sleep(min(interval, 0.05))

    def _fetch_snapshot(self) -> Optional[OnSensorSnapshot]:
        device = self._device
        if device is None:
            return None
        metadata = None
        if self._picam is not None and hasattr(self._picam, "capture_metadata"):
            try:
                metadata = self._picam.capture_metadata()
            except Exception:
                metadata = None
        if not metadata:
            return None
        outputs = None
        try:
            outputs = device.get_outputs(metadata)
        except Exception:
            outputs = None
        if outputs is None:
            return None
        detections: List[OnSensorDetection] = []
        boxes, scores, classes = self._unpack_outputs(outputs)
        for bbox, score, class_id in zip(boxes, scores, classes):
            if float(score) < float(self.cfg.confidence):
                continue
            label = self._label_for(int(class_id))
            if not self._should_emit(label):
                continue
            x1, y1, x2, y2 = [float(v) for v in bbox]
            detections.append(
                OnSensorDetection(
                    class_id=int(class_id),
                    label=label,
                    score=float(score),
                    bbox_xyxy_norm=(x1, y1, x2, y2),
                )
            )
        self._frame_id += 1
        width = int(metadata.get("ScalerCrop", [0, 0, 0, 0])[2]) if isinstance(metadata.get("ScalerCrop"), (list, tuple)) else 0
        height = int(metadata.get("ScalerCrop", [0, 0, 0, 0])[3]) if isinstance(metadata.get("ScalerCrop"), (list, tuple)) else 0
        return OnSensorSnapshot(
            ts=time.time(),
            frame_id=self._frame_id,
            width=width,
            height=height,
            detections=detections,
            backend="imx500",
        )

    def _unpack_outputs(self, outputs: Any) -> Tuple[List[List[float]], List[float], List[int]]:
        boxes: List[List[float]] = []
        scores: List[float] = []
        classes: List[int] = []
        try:
            if isinstance(outputs, (list, tuple)) and outputs:
                first = outputs[0]
                if isinstance(first, dict):
                    raw_boxes = first.get("boxes") or first.get("bboxes") or []
                    raw_scores = first.get("scores") or []
                    raw_classes = first.get("classes") or first.get("class_ids") or []
                    boxes = [list(b) for b in raw_boxes]
                    scores = [float(s) for s in raw_scores]
                    classes = [int(c) for c in raw_classes]
                else:
                    if len(outputs) >= 3:
                        raw_boxes, raw_scores, raw_classes = outputs[:3]
                        boxes = [list(b) for b in raw_boxes]
                        scores = [float(s) for s in raw_scores]
                        classes = [int(c) for c in raw_classes]
        except Exception:
            pass
        return boxes, scores, classes


__all__ = ["Imx500Config", "Imx500Runner", "IMX500_AVAILABLE", "IMX500_IMPORT_ERROR"]
