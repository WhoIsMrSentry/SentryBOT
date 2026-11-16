#!/usr/bin/env python3
"""
SentryBOT - Canlı Yüz Tanıma Doğrulama Test Aracı
------------------------------------------------
Kameradan canlı kare alır, kayıtlı yüzlerle karşılaştırır ve
tanıma sonucunu, skorunu ve kişi detaylarını ekrana basar.
"""
import os
import sys

# Proje kök dizinini ekle
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.vlm_bridge.services.face_manager import FaceManager
from modules.vlm_bridge.services.person_identity import PersonIdentity
from scripts._camera_capture_helper import capture_live_face_frame


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

    # 2. Kamerayı / Gateway üzerinden veya donanımdan güvenli yakala
    print("\n[INFO] Kamera başlatılıyor... Lütfen kameraya doğru bakın.")
    print("[INFO] Canlı tarama yapılıyor (en net kare yakalanıyor)...")

    best_name = "Unknown"
    best_score = 0.0

    def _score_verify_frame(candidate):
        nonlocal best_name, best_score
        name, score = face_mgr.identify_face_with_score(candidate)
        if name != "Unknown" and score > best_score:
            best_name = name
            best_score = score
            return True, score
        if score > best_score:
            best_score = score
            best_name = name
        return False, score

    frame = capture_live_face_frame(
        camera_num=0,
        max_attempts=25,
        poll_interval_s=0.15,
        frame_selector=_score_verify_frame,
        prefer_gateway=True,
    )
    if frame is not None and best_score == 0.0:
        # Frame Gateway /snap üzerinden tek seferde geldiyse doğrulama skorunu hesapla
        best_name, best_score = face_mgr.identify_face_with_score(frame)

    print("\n\n" + "=" * 60)
    print("                  TEST SONUCU")
    print("=" * 60)

    if frame is None:
        print("[HATA] Kameradan görüntü alınamadı.")
        return 3

    if best_name != "Unknown":
        person_rec = identity_mgr.get_person(best_name)
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
