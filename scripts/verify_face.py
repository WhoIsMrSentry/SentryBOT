#!/usr/bin/env python3
"""
SentryBOT - Canlı Yüz Tanıma Doğrulama Test Aracı
------------------------------------------------
Kameradan canlı kare alır, kayıtlı yüzlerle karşılaştırır ve
tanıma sonucunu, skorunu ve kişi detaylarını ekrana basar.
"""
import os
import sys
import time
import cv2
import numpy as np

# Proje kök dizinini ekle
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher
from modules.vlm_bridge.services.face_manager import FaceManager
from modules.vlm_bridge.services.person_identity import PersonIdentity


def main():
    print("=" * 60)
    print("       SENTRYBOT CANLI YÜZ TANIMA TEST ARACI")
    print("=" * 60)

    # 1. FaceManager ve PersonIdentity başlat
    face_mgr = FaceManager()
    identity_mgr = PersonIdentity()

    known = face_mgr.known_face_names
    print(f"[INFO] Hafızadaki Kayıtlı Kişiler ({len(known)}): {', '.join(known) if known else 'YOK'}")
    if not known:
        print("[UYARI] Henüz kayıtlı yüz bulunmuyor. Önce 'python scripts/enroll_face.py' çalıştırın.")
        return 1

    # 2. Kamerayı başlat
    cfg = CaptureConfig(camera_num=0, size=(1280, 720), frame_rate=15)
    pub = FramePublisher()
    cap = CameraCapture(cfg=cfg, publisher=pub)

    print("\n[INFO] Kamera başlatılıyor... Lütfen kameraya doğru bakın.")
    if not cap.start():
        print("[HATA] Kamera donanımı başlatılamadı.")
        return 2

    time.sleep(1.5)
    print("[INFO] Canlı tarama yapılıyor (en net kare yakalanıyor)...")

    frame = None
    best_name = "Unknown"
    best_score = 0.0

    try:
        for i in range(1, 25):
            time.sleep(0.15)
            jpeg_bytes = pub.get_jpeg()
            if jpeg_bytes:
                candidate = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                if candidate is not None:
                    name, score = face_mgr.identify_face_with_score(candidate)
                    if name != "Unknown" and score > best_score:
                        best_name = name
                        best_score = score
                        frame = candidate
                        break
                    elif score > best_score:
                        best_score = score
                        best_name = name
                        frame = candidate
            sys.stdout.write(".")
            sys.stdout.flush()
    finally:
        cap.stop()

    print("\n\n" + "=" * 60)
    print("                  TEST SONUCU")
    print("=" * 60)

    if frame is None:
        print("[HATA] Kameradan görüntü alınamadı.")
        return 3

    if best_name != "Unknown":
        rel = getattr(person_rec.relationship, "value", str(person_rec.relationship)) if person_rec else "bilinmiyor"
        level = getattr(person_rec, "recognition_level", 1) if person_rec else 1

        print(f"  [BAŞARILI] YÜZ TANINDI!")
        print(f"  * Tanınan Kişi:       {best_name}")
        print(f"  * Eşleşme Skoru:      %{best_score * 100:.1f}")
        print(f"  * İlişki / Rol:       {rel.upper()}")
        print(f"  * Tanınma Seviyesi:   {level} / 5")
        if rel == "owner":
            print(f"  * Robot Tepkisi:      EN YÜKSEK ÖNCELİK (Sahip Karşılama, Gökkuşağı LED, Mutlu Gözler)")
    else:
        print(f"  [BİLGİ] Yüz algılandı ancak kayıtlı bir kişiyle eşleşmedi (Skor: %{best_score * 100:.1f}).")
        print("  Lütfen ışıklandırmanın yeterli olduğundan ve yüzünüzün kameraya tam baktığından emin olun.")

    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
