"""Remote Vision Client (YOLO'suz)

Harici bir makinede calisir:
- Robot kamera akisini alir.
- OpenCV Haar ile yuz/insan adayi bulur.
- Sonuclari robot uzerindeki /vlm/results endpointine yollar.

Not:
- Bu ornek yalnizca hafif bir feeder'dir.
- Nesne siniflandirma icin harici bir VLM pipeline baglanabilir.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import cv2
import requests

VLM_BRIDGE_URL = "http://ROBOT_IP:8099/vlm/results"  # Degistir
AUTH_TOKEN = "changeme"  # vlm_bridge remote.auth_token ile ayni
CAMERA_FEED = "http://ROBOT_IP:8080/camera/video_feed"  # Gateway kamera stream


def open_mjpeg(url: str):
    return cv2.VideoCapture(url)


def _detect_faces(frame) -> List[Dict[str, Any]]:
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(56, 56))

    out: List[Dict[str, Any]] = []
    for (x, y, w, h) in faces:
        out.append(
            {
                "label": "person",
                "name": "Unknown",
                "confidence": 0.6,
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
            }
        )
    return out


def run_loop() -> None:
    cap = open_mjpeg(CAMERA_FEED)
    if not cap.isOpened():
        raise RuntimeError("Kamera akisi acilamadi")

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(1.0)
            continue

        objects = _detect_faces(frame)
        payload = {"objects": objects, "timestamp": time.time()}
        try:
            requests.post(
                VLM_BRIDGE_URL,
                json=payload,
                headers={"X-Auth-Token": AUTH_TOKEN},
                timeout=1.0,
            )
        except Exception:
            pass

        time.sleep(0.06)


if __name__ == "__main__":
    run_loop()
