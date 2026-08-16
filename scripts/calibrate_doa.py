#!/usr/bin/env python3
"""
SentryBOT Direction of Arrival (DoA) & Ses Yönü Kalibrasyon Scripti
-------------------------------------------------------------------
Bu script, mikrofonların sağ/sol kanal ayrımını, faz farklarını ve
gecikmelerini (GCC-PHAT) kalibre etmek için adım adım kullanıcıdan
ses kayıtları alır ve analiz eder.

Adımlar:
1. Sağ Yakından Konuş
2. Sağ Uzaktan Konuş
3. Sol Yakından Konuş
4. Sol Uzaktan Konuş
5. Orta Yakından Konuş
6. Orta Uzaktan Konuş
"""
import os
import sys
import time
import wave
import math
import numpy as np

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.speech.services.direction import DirectionEstimator, ArrayGeometry
from modules.speech.services.audio_capture import AudioCapture, AudioConfig

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "audio_calibration")
os.makedirs(OUTPUT_DIR, exist_ok=True)

STEPS = [
    {
        "id": "sag_yakin",
        "title": "Sağ Yakından Konuş",
        "desc": "Robotun SAĞ tarafına YAKLAŞIN (~30-50 cm) ve mikrofona doğru net bir sesle konuşun.",
        "expected": "sag",
    },
    {
        "id": "sag_uzak",
        "title": "Sağ Uzaktan Konuş",
        "desc": "Robotun SAĞ tarafında UZAKLAŞIN (~1.5-2 metre) ve normal bir ses tonuyla konuşun.",
        "expected": "sag",
    },
    {
        "id": "sol_yakin",
        "title": "Sol Yakından Konuş",
        "desc": "Robotun SOL tarafına YAKLAŞIN (~30-50 cm) ve mikrofona doğru net bir sesle konuşun.",
        "expected": "sol",
    },
    {
        "id": "sol_uzak",
        "title": "Sol Uzaktan Konuş",
        "desc": "Robotun SOL tarafında UZAKLAŞIN (~1.5-2 metre) ve normal bir ses tonuyla konuşun.",
        "expected": "sol",
    },
    {
        "id": "orta_yakin",
        "title": "Orta Yakından Konuş",
        "desc": "Robotun TAM KARŞISINA YAKLAŞIN (~30-50 cm) ve mikrofona doğru konuşun.",
        "expected": "orta",
    },
    {
        "id": "orta_uzak",
        "title": "Orta Uzaktan Konuş",
        "desc": "Robotun TAM KARŞISINDA UZAKTA DURUN (~1.5-2 metre) ve mikrofona doğru konuşun.",
        "expected": "orta",
    },
]


def save_wav(filename: str, pcm_bytes: bytes, rate: int = 16000, channels: int = 2):
    path = os.path.join(OUTPUT_DIR, filename)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)
    return path


def analyze_recording(pcm_bytes: bytes, rate: int = 16000) -> dict:
    data = np.frombuffer(pcm_bytes, dtype=np.int16)
    if data.size % 2 != 0:
        data = data[:-1]

    L = data[0::2].astype(np.float32)
    R = data[1::2].astype(np.float32)

    rms_L = float(np.sqrt(np.mean(L**2))) if L.size > 0 else 0.0
    rms_R = float(np.sqrt(np.mean(R**2))) if R.size > 0 else 0.0
    ratio_LR = (rms_L / (rms_R + 1e-6))

    # Calculate DoA with interpolation for fine sub-sample precision
    estimator = DirectionEstimator(sample_rate=rate, geometry=ArrayGeometry(mic_distance_m=0.06))
    
    # Calculate angle across 0.2s windows and take robust median
    win_size = int(rate * 0.25) * 2  # stereo samples
    angles = []
    for i in range(0, len(data) - win_size, win_size // 2):
        chunk = data[i : i + win_size].tobytes()
        try:
            ang = estimator.estimate(chunk)
            # Filter silence/outliers
            chunk_arr = np.frombuffer(chunk, dtype=np.int16)
            if np.mean(np.abs(chunk_arr)) > 200:
                angles.append(ang)
        except Exception:
            pass

    median_angle = float(np.median(angles)) if angles else 0.0
    
    if median_angle > 15.0 or ratio_LR < 0.8:
        detected_side = "SAĞ"
    elif median_angle < -15.0 or ratio_LR > 1.25:
        detected_side = "SOL"
    else:
        detected_side = "ORTA"

    return {
        "rms_L": rms_L,
        "rms_R": rms_R,
        "ratio_LR": ratio_LR,
        "angle": median_angle,
        "side": detected_side,
        "num_valid_windows": len(angles),
    }


def main():
    print("=" * 65)
    print("      SENTRYBOT SES YÖNÜ (DoA) KALİBRASYON PROGRAMI")
    print("=" * 65)
    print("Bu test robotun stereo mikrofonlarını kalibre edecek.")
    print("Toplam 6 adım gerçekleştirilecektir.\n")

    # Initialize AudioCapture
    cfg = AudioConfig(device="plughw:0,0", samplerate=16000, channels=2, frame_ms=30)
    capture = AudioCapture(cfg)
    print(f"[INFO] Mikrofon başlatılıyor (Cihaz: {cfg.device}, {cfg.samplerate}Hz, Stereo)...")
    if not capture.start():
        print(f"[WARN] ALSA '{cfg.device}' başlatılamadı, varsayılan cihaz deneniyor...")
        cfg.device = None
        capture = AudioCapture(cfg)
        if not capture.start():
            print("[HATA] Mikrofon açılamadı! Lütfen mikrofon bağlantılarını kontrol edin.")
            return 1

    time.sleep(1.0)
    results = []

    try:
        for idx, step in enumerate(STEPS, 1):
            print("\n" + "-" * 60)
            print(f" ADIM {idx}/6: {step['title'].upper()}")
            print(f" Talimat: {step['desc']}")
            print("-" * 60)

            # 1. User approval
            input(">> Hazırsanız [ENTER] tuşuna basın...")

            # 2. Wait 2 seconds with countdown
            print("Kayıt başlıyor:")
            for s in [2, 1]:
                print(f"  [ {s} ] saniye...")
                time.sleep(1.0)
            print("  >> [KAYIT BAŞLADI - 5 SANİYE KONUŞUN] <<")

            # 3. Record 5 seconds
            frames = []
            start_time = time.time()
            # Clear old buffer
            while capture.read():
                pass

            while time.time() - start_time < 5.0:
                frame = capture.read()
                if frame:
                    frames.append(frame)
                time.sleep(0.015)

            print("  >> [KAYIT TAMAMLANDI] <<\n")

            pcm_data = b"".join(frames)
            wav_file = f"{idx}_{step['id']}.wav"
            saved_path = save_wav(wav_file, pcm_data, rate=cfg.samplerate, channels=2)

            analysis = analyze_recording(pcm_data, rate=cfg.samplerate)
            analysis["step"] = step["title"]
            analysis["expected"] = step["expected"]
            analysis["wav"] = saved_path
            results.append(analysis)

            print(f"  [Analiz Sonucu]")
            print(f"    - Sol Kanal RMS:     {analysis['rms_L']:.1f}")
            print(f"    - Sağ Kanal RMS:     {analysis['rms_R']:.1f}")
            print(f"    - L/R Oranı:         {analysis['ratio_LR']:.2f}")
            print(f"    - Hesaplanan Açı:    {analysis['angle']:+.1f}°")
            print(f"    - Algılanan Yön:     {analysis['side']}")

    finally:
        capture.stop()

    print("\n" + "=" * 65)
    print("             KALİBRASYON RAPORU VE ÖZET")
    print("=" * 65)
    for r in results:
        print(f" * {r['step']:<24}: Açı={r['angle']:+5.1f}°, Oran(L/R)={r['ratio_LR']:4.2f} -> Yön: {r['side']}")

    print("\n[BİLGİ] Tüm ses kayıtları 'data/audio_calibration/' klasörüne kaydedildi.")
    print("Kalibrasyon tamamlandı!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
