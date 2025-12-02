"""Remote Vision Client

Harici makinede çalışır: Robotun kamera akışını çeker (ör: gateway /camera/video_feed),
YOLO + opsiyonel depth/OCR/yüz tanıma (daha ağır modeller) uygular, sonuçları
robot üzerindeki vision_bridge modülüne POST eder.

Bu örnek hafif temeldir; üretimde asenkron + yeniden bağlanma + hata geri durumu eklenmelidir.
"""
from __future__ import annotations
import cv2
import time
import requests
from typing import List, Dict, Any

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # Kullanıcı model yüklemeyi ayarlamalı

VISION_BRIDGE_URL = "http://ROBOT_IP:8099/vision/results"  # Değiştir
AUTH_TOKEN = "changeme"  # vision_bridge remote.auth_token ile aynı
CAMERA_FEED = "http://ROBOT_IP:8080/camera/video_feed"  # Gateway kamera stream (örnek)
MODEL_PATH = "yolov8m.pt"  # Remote cihazda daha ağır model

def open_mjpeg(url: str):
    return cv2.VideoCapture(url)

def run_loop():
    if YOLO is None:
        raise RuntimeError("ultralytics paketi gerekli")
    model = YOLO(MODEL_PATH)
    cap = open_mjpeg(CAMERA_FEED)
    if not cap.isOpened():
        raise RuntimeError("Kamera akışı açılamadı")
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(1.0)
            continue
        results = model(frame, verbose=False)
        objects: List[Dict[str, Any]] = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                objects.append({
                    "label": label,
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                })
        payload = {"objects": objects, "timestamp": time.time()}
        try:
            requests.post(VISION_BRIDGE_URL, json=payload, headers={"X-Auth-Token": AUTH_TOKEN}, timeout=1.0)
        except Exception:
            pass
        time.sleep(0.05)

if __name__ == "__main__":
    run_loop()