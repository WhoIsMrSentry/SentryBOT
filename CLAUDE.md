# SentryBOT — Claude Code Entegrasyonu

SentryBOT, Raspberry Pi 5 üzerinde çalışan modüler bir otonom robot platformudur. 29 Python modülü, Arduino seri iletişim, OpenCV görüntü işleme ve Ollama LLM entegrasyonu içerir.

## Kritik Kurallar
1. **DryCode** — Tekrar yok, tek sorumluluk, kısa fonksiyonlar
2. **Modül yapısı** — `x<Name>Service.py` + `config_loader.py` + `config/config.yml` + `api/router.py`
3. **Arduino kontratı** — `modules/arduino_serial/contract.py` builder zorunlu, elle payload YASAK
4. **Config** — Hardcode YASAK, YAML'den oku
5. **Test** — Her modülde `tests/test_smoke.py` zorunlu

## 📁 Tek Merkez: `.sentrybot/`

Tüm agent, skill, context ve template dosyaları **tek dizinde** toplanmıştır:

```
.sentrybot/
├── agents/          # 5 iş akışı yöneticisi
├── skills/          # 12 adım adım prosedür
├── context/         # Modül listesi, API haritası, mimari, kurallar
└── templates/       # Modül iskelet şablonları
```

### Görev Başlarken
1. `.sentrybot/context/module-registry.md` → 29 modül listesi
2. `.sentrybot/context/conventions.md` → Tüm kurallar
3. İlgili agent dosyasını oku → İş akışını takip et
4. İlgili skill dosyalarını takip et → Adım adım uygula

### Sık Kullanılan Komutlar
```bash
python -m pytest modules/ -q --maxfail=1       # Tüm testler
python -m pytest modules/<mod>/tests/ -v        # Tek modül
python run_robot.py                             # Robot başlat
```
