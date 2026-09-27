#!/usr/bin/env python3
"""SentryBOT Laya (System 1) Karar Motoru Prototip Testi.

Bu script, Laya System 1 karar modelini SentryBOT'un gerçek modül ve
girdi senaryoları üzerinde yerel olarak test eder ve karar süresini (ms) ölçer.
"""

import sys
import time
from typing import Dict, Any

def test_laya():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("=" * 70, flush=True)
    print("SentryBOT - Laya System 1 Karar Motoru Testi Baslatiliyor...", flush=True)
    print("=" * 70, flush=True)

    try:
        import laya
        from laya import Router
        print(f"[+] Laya kütüphanesi başarıyla yüklendi (Sürüm: {getattr(laya, '__version__', 'unknown')})")
    except ImportError as e:
        print(f"[-] HATA: Laya kütüphanesi import edilemedi: {e}")
        print("Lütfen 'pip install laya' komutunun tamamlandığından emin olun.")
        sys.exit(1)

    print("[*] Laya Multilingual modeli yükleniyor...", flush=True)
    start_load = time.perf_counter()
    try:
        import os
        model_path = os.path.expanduser(
            r"~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/5e7b2b1b8ca2ecdd3f2322d94069c9b6ce7e844b/multilingual"
        )
        if os.path.isdir(model_path):
            agent = laya.load(model_path)
        else:
            agent = laya.load("convaiinnovations/laya", subfolder="multilingual")
        load_time = (time.perf_counter() - start_load) * 1000
        print(f"[+] Laya Multilingual Model hazır! Cihaz: {agent.device} (Yükleme süresi: {load_time:.2f} ms)\n", flush=True)
    except Exception as e:
        print(f"[-] Model yükleme hatası: {e}", flush=True)
        print("Lütfen internet bağlantısını kontrol edin.", flush=True)
        sys.exit(1)

    # SentryBOT için Karar Soruları (System 1 Specification)
    questions = {
        "target_module": {
            "type": "choice",
            "instructions": "Bu kullanıcı girdisi SentryBOT robotunun hangi donanım/eylem modülüne ait?",
            "criteria": {
                "neopixel": "Işık, renk, parlaklık veya LED animasyonlarını değiştirme",
                "arduino_serial": "Kafa hareketi, pan/tilt, motor, yürüme veya durdurma",
                "emergency_stop": "Acil durum, anında durma, tehlike, kapatma",
                "speech_tts": "Robotun bir şey söylemesini, konuşmasını isteme",
                "system2_chat": "Genel sohbet, soru-cevap, felsefe, akıl yürütme veya şaka"
            }
        },
        "is_direct_command": {
            "type": "choice",
            "instructions": "Bu girdi doğrudan hızlı icra edilecek bir donanım komutu mu yoksa derin sohbet mi?",
            "criteria": {
                "direct_action": "Hemen uygulanacak net bir donanım/refleks komutu",
                "conversation": "Düşünce, cevap veya diyalog gerektiren sohbet/soru"
            }
        },
        "affective_event": {
            "type": "choice",
            "instructions": "Kullanıcının robota karşı duygusal/sosyal tutumu nedir?",
            "criteria": {
                "user_praise": "Övgü, sevgi, aferin, teşekkür, iltifat veya sevme",
                "user_rude": "Kabalık, hakaret, küfür, susturma veya kızgınlık",
                "neutral": "Duygusal olmayan nötr komut veya bilgi sorusu"
            }
        },
        "urgency": {
            "type": "score",
            "instructions": "Bu girdinin aciliyet ve tehlike seviyesi nedir?",
            "criteria": [
                "sakin, normal konuşma veya bilgi sorusu",
                "normal günlük hareket veya rutin eylem komutu",
                "hızlı yapılması istenen öncelikli komut",
                "son derece acil, tehlike, kaza riski veya anında durdurma"
            ]
        }
    }

    # Test Senaryoları (SentryBOT Gerçek Kullanıcı Örnekleri)
    test_cases = [
        {
            "name": "Senaryo 1: NeoPixel Işık Değişimi",
            "text": "Sentry ışıkları hemen kırmızı yap ve uyarı moduna geç",
            "expected_module": "neopixel"
        },
        {
            "name": "Senaryo 2: Kafa / Servo Hareketi",
            "text": "Kafanı biraz yukarı kaldır ve sola doğru bak",
            "expected_module": "arduino_serial"
        },
        {
            "name": "Senaryo 3: Acil Durdurma (E-Stop)",
            "text": "Hemen dur acil durum motorları kapat çarpacaksın!",
            "expected_module": "emergency_stop"
        },
        {
            "name": "Senaryo 4: Sevgi / Övgü (Affective Appraisal)",
            "text": "Harika bir iş çıkardın, sen çok tatlı ve akıllı bir robotsun aferin!",
            "expected_module": "system2_chat / affective"
        },
        {
            "name": "Senaryo 5: Hakaret / Kabalık (Affective Appraisal)",
            "text": "Ne kadar aptal ve işe yaramaz bir robotsun sus artık kapa çeneni!",
            "expected_module": "system2_chat / affective"
        },
        {
            "name": "Senaryo 6: Derin Sohbet (System 2 LLM'e Gidecek)",
            "text": "Yapay zekanın geleceği hakkında ne düşünüyorsun dostum, insanlar gibi hissedebilecek misin?",
            "expected_module": "system2_chat"
        },
        {
            "name": "Senaryo 7: Konuşma Komutu",
            "text": "Odaya gelen herkese hoş geldiniz efendim de",
            "expected_module": "speech_tts"
        }
    ]

    total_latency = 0.0

    for i, tc in enumerate(test_cases, 1):
        print("-" * 70)
        print(f"[{i}/{len(test_cases)}] {tc['name']}")
        print(f"Girdi: \"{tc['text']}\"")

        state = {"text": tc["text"]}

        t0 = time.perf_counter()
        raw_res = agent.system_one(state, questions)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_latency += elapsed_ms
        result = raw_res.get("answers", {})

        # Çıktıları yazdır
        target = result.get("target_module", {})
        direct = result.get("is_direct_command", {})
        affect = result.get("affective_event", {})
        urgency = result.get("urgency", {})

        target_val = target.get("choice") or target.get("value")
        direct_val = direct.get("choice") or direct.get("value")
        affect_val = affect.get("choice") or affect.get("value")
        urgency_val = urgency.get("score") if "score" in urgency else urgency.get("value", 0)

        print(f"[*] Karar Suresi: {elapsed_ms:.2f} ms", flush=True)
        print(f"[>] Hedef Modul : {target_val} (Guven: {target.get('confidence', 0):.2f})", flush=True)
        print(f"[>] Eylem Turu  : {direct_val} (Guven: {direct.get('confidence', 0):.2f})", flush=True)
        print(f"[>] Duygu Olayi : {affect_val} (Guven: {affect.get('confidence', 0):.2f})", flush=True)
        print(f"[!] Aciliyet    : {urgency_val:.2f} (Guven: {urgency.get('confidence', 0):.2f})", flush=True)

    avg_latency = total_latency / len(test_cases)
    print("=" * 70, flush=True)
    print(f"TEST TAMAMLANDI! Ortalama Karar Süresi: {avg_latency:.2f} ms", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    test_laya()
