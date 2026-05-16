# SentryBOT — Modül Kayıt Defteri (Module Registry)

> AI asistanlar bu dosyayı okuyarak projedeki tüm modülleri, portlarını, görevlerini ve bağımlılıklarını hızla öğrenir.

## Modül Listesi

| # | Modül | Port | Katman | Görev | Arduino Kullanır | Kilit Bağımlılıklar |
|---|-------|------|--------|-------|-----------------|---------------------|
| 1 | `gateway` | 8080 | Çekirdek | FastAPI API bootstrapper, tüm modülleri mount eder | Hayır | Tüm modüller |
| 2 | `autonomy` | — | Çekirdek | Sense-Think-Act beyin döngüsü, duygu motoru, LLM kararları | Evet | ollama, speak, vlm_bridge, arduino_serial |
| 3 | `agent_core` | — | Çekirdek | 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling | Hayır | ollama, autonomy |
| 4 | `arduino_serial` | — | Eylem | NDJSON seri haberleşme, komut/yanıt kuyruğu | **Kaynak** | — |
| 5 | `camera` | — | Algı | MJPEG kamera stream, auto-recovery | Hayır | — |
| 6 | `vlm_bridge` | 8101 | Algı | OpenCV yüz algılama, ORB/FLANN eşleme, CSRT takip, remote VLM | Evet (pan/tilt) | camera, arduino_serial, ollama |
| 7 | `speech` | 8082 | Ses/Dil | Çok kanallı ASR, Vosk/Whisper, ses yönü (DOA) | Hayır | — |
| 8 | `speak` | 8083 | Ses/Dil | TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı | Hayır | neopixel (liveliness) |
| 9 | `wakeword` | — | Ses/Dil | "Hey Sentry" sürekli dinleme (Porcupine/Snowboy) | Evet (buzzer) | speech, arduino_serial |
| 10 | `ollama` | 8099 | AI/RAG | Ollama LLM chat, persona yönetimi, JSON/XML parse | Hayır | — |
| 11 | `neopixel` | — | Eylem | 23 duygu paleti, SPI LED animasyonları | Hayır | — |
| 12 | `interactions` | — | Etkileşim | CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme | Hayır | neopixel, hardware |
| 13 | `animate` | — | Eylem | YAML servo animasyon oynatıcı | Evet | arduino_serial |
| 14 | `state_manager` | — | Çekirdek | Thread-safe global durum deposu, pub/sub | Hayır | — |
| 15 | `piservo` | — | Eylem | Raspberry Pi GPIO PWM kulak servoları | Hayır | — |
| 16 | `oled_faces` | — | Eylem | OLED ekran yüz ifadeleri | Hayır | — |
| 17 | `hardware` | — | Algı | CPU/RAM/sıcaklık bilgisi, I2C tarama | Hayır | — |
| 18 | `config_center` | — | Arka Plan | Merkezi config okuma/yazma, hot-reload | Hayır | — |
| 19 | `diagnostics` | — | Arka Plan | Sistem sağlık testi (Arduino, kamera, Ollama) | Dolaylı | arduino_serial, camera, ollama |
| 20 | `scheduler` | — | Arka Plan | Cron benzeri zamanlayıcı | Hayır | — |
| 21 | `notifier` | — | Arka Plan | Telegram/Discord bildirim gönderici | Hayır | — |
| 22 | `logwrapper` | — | Arka Plan | WebSocket log yayını, merkezi loglama | Hayır | — |
| 23 | `telemetry` | — | Arka Plan | Prometheus formatında metrik toplama | Hayır | — |
| 24 | `ota` | — | Arka Plan | Over-the-air güncelleme, checksum doğrulama | Hayır | — |
| 25 | `mutagen` | — | Arka Plan | PC↔Pi dosya senkronizasyonu | Hayır | — |
| 26 | `calibration` | — | Arka Plan | Servo kalibrasyon modu | Evet | arduino_serial |
| 27 | `esp_link` | — | Etkileşim | ESP32 köprü iletişimi (mDNS web remote) | Dolaylı | — |
| 28 | `social_db` | — | Veri | SQLite kişi hafızası, ilişki/tanıma seviyeleri | Hayır | — |
| 29 | `admin_ui` | — | Etkileşim | Web yönetim paneli (statik dosyalar) | Hayır | gateway |

## Mimari Katmanlar

```
1. ALGI (Sense)     → camera, speech, vlm_bridge, wakeword, hardware
2. BEYİN (Core)     → gateway, autonomy, agent_core, state_manager, config_center
3. AI / RAG         → ollama
4. EYLEM (Act)      → arduino_serial, animate, neopixel, speak, piservo, oled_faces
5. ARKA PLAN (Bg)   → scheduler, diagnostics, logwrapper, telemetry, ota, mutagen,
                       calibration, notifier, esp_link, social_db, admin_ui, interactions
```

## Modül Yapı Kuralı (Standart Şablon)

Her modül şu dosya yapısına uyar:

```
modules/<module_name>/
├── __init__.py                     # Re-export, versiyon bilgisi
├── x<ModuleName>Service.py         # Ana servis başlatıcı
├── config_loader.py                # config/config.yml okuyucu
├── config/
│   ├── config.yml                  # Modüle özgü ayarlar
│   └── README.md                   # (opsiyonel) config açıklaması
├── api/
│   ├── __init__.py
│   └── router.py                   # FastAPI router endpoint'leri
├── services/
│   ├── __init__.py
│   └── ...                         # İş mantığı sınıfları
├── tests/
│   └── test_smoke.py               # Temel testler
├── architecture_<module_name>.md   # Mimari dokümantasyon
└── README.md                       # Kullanım kılavuzu
```

## Arduino Kontratı Kullanan Modüller

Bu modüller `modules/arduino_serial/contract.py` builder fonksiyonlarını kullanmak zorundadır:
- `arduino_serial` (kaynak)
- `autonomy`
- `speech`
- `vlm_bridge`
- `animate`
- `calibration`
- `wakeword`
