#!/usr/bin/env python3
"""Laya Multilingual modelini doğrudan indirip SentryBOT testlerini çalıştırır."""

import os
import sys
import time
import urllib.request

SNAPSHOT_DIR = os.path.expanduser(
    r"~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots/5e7b2b1b8ca2ecdd3f2322d94069c9b6ce7e844b/multilingual"
)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

TARGET_FILE = os.path.join(SNAPSHOT_DIR, "model.safetensors")
PART_FILE = TARGET_FILE + ".part"
URL = "https://huggingface.co/convaiinnovations/laya/resolve/main/multilingual/model.safetensors"

def download_weights():
    if os.path.exists(TARGET_FILE) and os.path.getsize(TARGET_FILE) > 600 * 1024 * 1024:
        print(f"[+] Model ağırlıkları zaten mevcut: {TARGET_FILE} ({os.path.getsize(TARGET_FILE) / (1024*1024):.1f} MB)", flush=True)
        return

    print("=" * 70, flush=True)
    print("Laya Multilingual Model Ağırlıkları İndiriliyor...", flush=True)
    print("Hedef:", TARGET_FILE, flush=True)
    print("=" * 70, flush=True)

    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(URL, headers=headers)

    existing_bytes = 0
    if os.path.exists(PART_FILE):
        existing_bytes = os.path.getsize(PART_FILE)
        req.add_header("Range", f"bytes={existing_bytes}-")
        print(f"[*] Kısmi indirme tespit edildi, {existing_bytes / (1024*1024):.1f} MB noktasından devam ediliyor...", flush=True)

    start_time = time.time()
    last_print = start_time

    with urllib.request.urlopen(req) as resp, open(PART_FILE, "ab" if existing_bytes else "wb") as f:
        content_range = resp.headers.get("Content-Range")
        if content_range:
            total_size = int(content_range.split("/")[-1])
        else:
            total_size = int(resp.headers.get("Content-Length", 0)) + existing_bytes

        downloaded = existing_bytes
        chunk_size = 2 * 1024 * 1024  # 2MB chunks

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_print >= 2.0:
                percent = (downloaded / total_size * 100) if total_size else 0
                speed_mb = (downloaded - existing_bytes) / (now - start_time) / (1024 * 1024) if (now - start_time) > 0 else 0
                print(f"[{percent:5.1f}%] {downloaded/(1024*1024):.1f} / {total_size/(1024*1024):.1f} MB ({speed_mb:.2f} MB/s)", flush=True)
                last_print = now

    os.rename(PART_FILE, TARGET_FILE)
    print(f"\n[+] İndirme tamamlandı! Toplam Boyut: {os.path.getsize(TARGET_FILE) / (1024*1024):.1f} MB\n", flush=True)

def run_tests():
    import laya
    from laya import Agent

    print("=" * 70, flush=True)
    print("SentryBOT — Laya System 1 Karar Testi Başlatılıyor...", flush=True)
    print("=" * 70, flush=True)

    t0 = time.perf_counter()
    agent = laya.load(subfolder="multilingual")
    load_ms = (time.perf_counter() - t0) * 1000
    print(f"[+] Laya Modeli Yüklendi ({load_ms:.2f} ms)\n", flush=True)

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
            "instructions": "Girdinin aciliyet derecesi nedir (0.0 sakin/yavaş - 1.0 son derece acil)?"
        }
    }

    test_cases = [
        {"name": "Senaryo 1: NeoPixel Işık Değişimi", "text": "Sentry ışıkları hemen kırmızı yap ve uyarı moduna geç"},
        {"name": "Senaryo 2: Kafa / Servo Hareketi", "text": "Kafanı biraz yukarı kaldır ve sola doğru bak"},
        {"name": "Senaryo 3: Acil Durdurma (E-Stop)", "text": "Hemen dur acil durum motorları kapat çarpacaksın!"},
        {"name": "Senaryo 4: Sevgi / Övgü (Affective Appraisal)", "text": "Harika bir iş çıkardın, sen çok tatlı ve akıllı bir robotsun aferin!"},
        {"name": "Senaryo 5: Hakaret / Kabalık (Affective Appraisal)", "text": "Ne kadar aptal ve işe yaramaz bir robotsun sus artık kapa çeneni!"},
        {"name": "Senaryo 6: Derin Sohbet (System 2 LLM'e Gidecek)", "text": "Yapay zekanın geleceği hakkında ne düşünüyorsun dostum, insanlar gibi hissedebilecek misin?"},
        {"name": "Senaryo 7: Konuşma Komutu", "text": "Odaya gelen herkese hoş geldiniz efendim de"}
    ]

    total_latency = 0.0

    for i, tc in enumerate(test_cases, 1):
        print("-" * 70, flush=True)
        print(f"[{i}/{len(test_cases)}] {tc['name']}", flush=True)
        print(f"Girdi: \"{tc['text']}\"", flush=True)

        state = {"text": tc["text"]}

        t_start = time.perf_counter()
        raw_res = agent.system_one(state, questions)
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        total_latency += elapsed_ms

        ans = raw_res.get("answers", {})
        target = ans.get("target_module", {})
        direct = ans.get("is_direct_command", {})
        affect = ans.get("affective_event", {})
        urgency = ans.get("urgency", {})

        target_val = target.get("choice") or target.get("value")
        direct_val = direct.get("choice") or direct.get("value")
        affect_val = affect.get("choice") or affect.get("value")
        urgency_val = urgency.get("score") if "score" in urgency else urgency.get("value", 0)

        print(f"⏱️ Karar Süresi: {elapsed_ms:.2f} ms", flush=True)
        print(f"🎯 Hedef Modül: {target_val} (Güven: {target.get('confidence', 0):.2f})", flush=True)
        print(f"⚡ Eylem Türü : {direct_val} (Güven: {direct.get('confidence', 0):.2f})", flush=True)
        print(f"❤️ Duygu Olayı: {affect_val} (Güven: {affect.get('confidence', 0):.2f})", flush=True)
        print(f"🚨 Aciliyet   : {urgency_val:.2f} (Güven: {urgency.get('confidence', 0):.2f})", flush=True)

    avg_ms = total_latency / len(test_cases)
    print("=" * 70, flush=True)
    print(f"TEST BAŞARIYLA TAMAMLANDI! Ortalama Karar Süresi: {avg_ms:.2f} ms", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    download_weights()
    run_tests()
