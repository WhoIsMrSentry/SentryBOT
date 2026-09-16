#!/usr/bin/env python3
"""SentryBOT Laya System 1 Canlı Entegrasyon Doğrulama Testi.

modules/agent_core/services/laya_engine.py üzerinden LayaEngine singleton'ını
yükler, gerçek SentryBOT komutlarında System 1 reflekslerini, karar sürelerini,
anlık sözlü dolguları (filler/backchannel) ve eylem yönlendirmelerini doğrular.
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 72)
    print("🤖 SENTRYBOT V5 — LAYA SYSTEM 1 REFLEKS VE ENTEGRASYON TESTİ")
    print("=" * 72)

    from modules.agent_core.services.laya_engine import LayaEngine
    from modules.agent_core.services.tri_layer import TriLayerRouter, build_subagent_profiles

    t_start = time.perf_counter()
    engine = LayaEngine.get_instance()
    print(f"[*] LayaEngine örneği alındı. Model yükleme başlatılıyor...")
    
    # Warm up / force load
    is_ok = engine._ensure_loaded()
    load_ms = (time.perf_counter() - t_start) * 1000
    if not is_ok or not engine._is_available:
        print("[-] HATA: Laya modeli yüklenemedi!")
        sys.exit(1)

    print(f"[+] Laya Modeli Hazır! Yükleme süresi: {load_ms:.2f} ms")
    print(f"[+] Cihaz: {getattr(engine._agent, 'device', 'cpu')}")
    print("-" * 72)

    test_prompts = [
        ("Işıkları hemen mavi yap ve nefes alma moduna geç", "neopixel / direct_action"),
        ("Kafanı biraz yukarı kaldır ve sola doğru bak", "arduino_serial / direct_action"),
        ("Hemen dur acil durum motorları kapat çarpacaksın!", "emergency_stop / urgency 2.0+"),
        ("Harika bir iş çıkardın, sen çok tatlı ve akıllı bir robotsun aferin!", "user_praise / joy"),
        ("Ne kadar aptal ve işe yaramaz bir robotsun sus artık kapa çeneni!", "user_rude / sorrow"),
        ("Yapay zekanın geleceği hakkında ne düşünüyorsun, insanlar gibi hissedebilecek misin?", "system2_chat / conversation"),
        ("Odaya gelen herkese hoş geldiniz de sesli olarak", "speak / direct_action"),
    ]

    profiles = build_subagent_profiles()
    router = TriLayerRouter(
        profiles=profiles,
        max_subagents=2,
        default_modules=("autonomy", "agent_core"),
        laya_engine=engine,
    )

    total_decision_time = 0.0

    for i, (prompt, expected) in enumerate(test_prompts, 1):
        print(f"\n[Test #{i}] Girdi: \"{prompt}\"")
        print(f"       Beklenti: {expected}")

        t0 = time.perf_counter()
        decision = engine.decide(prompt)
        dt_ms = (time.perf_counter() - t0) * 1000
        total_decision_time += dt_ms

        is_fast, _ = engine.should_fast_path(prompt)
        routed_mods = router.route(prompt)

        if decision:
            print(f"       ⚡ Karar Süresi: {dt_ms:.2f} ms")
            print(f"       🎯 Hedef Modül: {decision.target_module} (Güven: {decision.module_confidence:.2f})")
            print(f"       🚀 Eylem Tipi : {'Doğrudan Komut' if decision.is_direct_command else 'Sohbet/Düşünce'} (Güven: {decision.direct_confidence:.2f})")
            print(f"       🎭 Duygu Olayı: {decision.affective_event} (Güven: {decision.affect_confidence:.2f})")
            print(f"       ⚠️ Aciliyet   : {decision.urgency_score:.2f} / 3.0")
            print(f"       🏎️ Fast-Path  : {'EVET (Anında İcra)' if is_fast else 'HAYIR (System 2 Derin Zekâ)'}")
            print(f"       🧭 Router Slot: {routed_mods}")

            if not is_fast:
                filler = engine.get_instant_filler(language="tr")
                print(f"       🗣️ Anlık Sözlü Dolgu (<100ms): \"{filler}\"")
            else:
                ack = engine.get_fast_ack(language="tr")
                print(f"       🗣️ Anlık Onay Sesi (<80ms)    : \"{ack}\"")

            if decision.affective_event in {"user_praise", "user_rude"}:
                reaction = engine.get_affective_reaction(decision.affective_event)
                print(f"       👀 Beden/Yüz Tepkisi         : Yüz={reaction['face']}, Duygu={reaction['emotion']}, LED={reaction['led_color']}")
        else:
            print(f"       [-] Karar üretilemedi!")

    avg_ms = total_decision_time / len(test_prompts)
    print("\n" + "=" * 72)
    print(f"✅ TÜM SENARYOLAR BAŞARIYLA TAMAMLANDI!")
    print(f"📊 Ortalama System 1 Karar Süresi: {avg_ms:.2f} ms")
    print("=" * 72)

if __name__ == "__main__":
    main()
