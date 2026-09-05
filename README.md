# <p align="center">
  <img src="https://raw.githubusercontent.com/WhoIsMrSentry/SentryBOT/dev/docs/assets/bot.gif" alt="SentryBOT demo" width="640" />
</p>

# SentryBOT – Modüler İki Ayaklı Yoldaş Robot Platformu

[![Pytest](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/pytest.yml/badge.svg?branch=main)](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/pytest.yml)
[![PR Labeler](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/labeler.yml/badge.svg)](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/labeler.yml)
[![Sync Labels](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/labels-sync.yml/badge.svg)](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/labels-sync.yml)
[![Relabel Open PRs](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/relabel-open-prs.yml/badge.svg)](https://github.com/WhoIsMrSentry/SentryBOT/actions/workflows/relabel-open-prs.yml)

[![License](https://img.shields.io/github/license/WhoIsMrSentry/SentryBOT)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/WhoIsMrSentry/SentryBOT)](https://github.com/WhoIsMrSentry/SentryBOT/commits/main)
[![Open Issues](https://img.shields.io/github/issues/WhoIsMrSentry/SentryBOT)](https://github.com/WhoIsMrSentry/SentryBOT/issues)
[![Closed Issues](https://img.shields.io/github/issues-closed/WhoIsMrSentry/SentryBOT)](https://github.com/WhoIsMrSentry/SentryBOT/issues?q=is%3Aissue+is%3Aclosed)
[![Open PRs](https://img.shields.io/github/issues-pr/WhoIsMrSentry/SentryBOT)](https://github.com/WhoIsMrSentry/SentryBOT/pulls)
[![Closed PRs](https://img.shields.io/github/issues-pr-closed/WhoIsMrSentry/SentryBOT)](https://github.com/WhoIsMrSentry/SentryBOT/pulls?q=is%3Apr+is%3Aclosed)

SentryBOT; Raspberry Pi 5 + Arduino tabanlı, modüler bir yoldaş robot ve servis mimarisidir. Tüm yetenekler bağımsız modüller hâlinde tasarlanır, tek bir Gateway üzerinden tek porttan API olarak sunulur. Donanım kontrolü Arduino ile yapılırken; konuşma tanıma/TTS, LED animasyonları, kamera ve LLM/RAG gibi fonksiyonlar Pi5 üzerinde mikro servisler olarak çalışır.

Ana hedefler:
- Basit, temiz, DryCode odaklı modüller
- Her modül hem kütüphane (import) hem servis (run) olarak çalışabilir
- Tüm konfigürasyonlar YAML dosyalarındadır ve gerektiğinde override edilebilir
- Donanım ağır işlerini Arduino üstlenir; görüntü işleme gibi pahalı işler gerekiyorsa dış istemcilere (PC) köprülenir


## Neler Yeni? (Öne Çıkan Son Geliştirmeler)

- **Tri-Layer Agent Mimarı (agent_core):** Robotun otonom kararları 3 katmanlı (Router/Planner, Uzman Sub-Agent'lar, Ana Persona) bir otonom ajan pipeline'ı ile yönetilir.
- **Social DB:** Eski JSON tabanlı izole hafızalar tek bir birleşik SQLite veritabanında toplandı. Kişiler, yüzler, ilişkiler, anılar ve ritüeller tek merkezden yönetiliyor.
- **OLED Faces:** SSD1306 I2C OLED için Pip tarzı prosedürel animasyonlu göz ve yüz ifadeleri eklendi. Duygusal ifadeler robotun durumuyla senkronize edilir.
- **Gelişmiş Otonomi ve Duygu Motoru (autonomy):** Robotun iç durumu (Mutluluk, Enerji, Merak, Korku) davranışlarını ve NeoPixel ışıklarını otomatik etkiler. Ses geldiğinde kafa çevirme, boşta kalınca iç çekme/etrafı izleme özellikleri aktiftir.
- **Wakeword Modülü:** OpenWakeWord destekli düşük güçlü arka plan dinleyicisi eklendi.
- **Semantik Router:** İstekler LLM tabanlı vektör/benzerlik ile en doğru sub-agent'a yönlendirilir.
- **Common Emotion Vocab:** Tüm modüller ortak bir duygu (emotion) sözlüğünü kullanır; gözler, ışıklar ve ses tonu birbiriyle uyumlu çalışır.
- Servo sürüşü I2C’ye taşındı (PCA9685, 50 Hz). Açı→mikrosaniye darbe haritalaması konfigüre edilebilir (min/max us).
- Çift “X‑cross” lazer eklendi: tekli ya da ikisi birden aç/kapa (firmware komut + Pi API).
- **Tam Yapılandırılmış Çıktı (Structured JSON)**: Ollama artık tüm yanıtlarını düşünce, vokal yanıt ve aksiyon içeren JSON formatında döner.
- **Sistem-Genel Modül Kontrolü**: Robot kendi modüllerini LLM kararlarıyla çalışma esnasında kapatıp açabilir.
- **Durum Kalıcılığı**: State Manager, global state'i sqlite/json backend ile restart sonrasında da saklar.
- **Gateway Güvenliği**: Gateway'e isteğe bağlı API anahtarı ve rol kontrolü eklendi; yazma uçları korunabilir.
- **VLM Mode Yönetimi**: Görüntü işleme yetenekleri ayrı ayrı açılıp kapatılabilir; pahalı işlemler ihtiyaca göre sınırlandırılır.
- **Multimodal Animasyon Senkronizasyonu**: Tek YAML akışında servolar, OLED göz ifadeleri ve NeoPixel ışık efektleri zaman uyumlu (time-coded) çalışır.


## Mimari Genel Bakış

- Donanım: Raspberry Pi 5 (ana bilgisayar) + Arduino (ör. Mega) kontrol kartı
- İletişim: Arduino ile NDJSON seri köprü; modüller arası HTTP (FastAPI)
- Gateway: Tüm modül router’larını tek FastAPI sürecinde birleştirir (varsayılan: 0.0.0.0:8080)
- Konfigürasyon: Her modül altında `config/config.yml`; merkezi düzenleme için Config Center
- Loglama: Merkezi log wrapper; dosya + bellek içi halka buffer

Başlatıcı akış (varsayılan): `sentrybot.py` -> TUI (Control Center) arayüzünü başlatır ve arka planda run_robot.py'yi çalıştırır.


## Robot Ne Yapar? (Yetenekler)

Algılama, karar ve ifade zinciriyle çalışan SentryBOT’un yetenekleri modüllere ayrılmıştır. Aşağıda her bir alan için kapsam, tipik veri akışı, önemli uç noktalar ve sınırlar özetlenmiştir.

- Hareket/Donanım
	- Arduino Seri Köprü (modules/arduino_serial)
		- Kapsam: servo/stepper sürüş, IK pozları, otur/kal kalk, IMU okuma, telemetry, emergency stop.
		- Veri akışı: Pi5 ↔ Arduino NDJSON satır tabanlı mesajlar; arkaplanda non-blocking okuyucu, heartbeat.
		- Örnek: POST `/arduino/request` body `{ "cmd": "set_pose", "pose":[...], "duration_ms":1200 }`
		- Sınırlar: Seri port stabilitesi; AUTO port bulma başarısızsa `ARDUINO_PORT` ile zorlayın.
	- PiServo “Kulaklar” (modules/piservo)
		- Kapsam: sol/sağ servo ile duygu jestleri ve basit jestler (wakeword/sound).
		- API: `/piservo/set?left=90&right=90`, `/piservo/emotion?name=joy`
		- Sınırlar: Donanım yoksa simülatör modunda çalışır; PWM/angle sınırları config ile belirlenir.
	- Teşhis & Zamanlama (modules/diagnostics, modules/scheduler)
		- Diagnostics API: `/diagnostics/run`, `/diagnostics/report` — modül sağlıklarını zincir hâlinde kontrol eder; gecikme ve tekrar eden hataları da değerlendirir.
		- Scheduler API: `/scheduler/jobs` — basit async periyodik görevler, HTTP ping işleri; runtime görev ekleme/silme de desteklenir.

- Duyular
	- Kamera (modules/camera)
		- Kapsam: PiCamera2/OpenCV backend; çözünürlük, FPS, JPEG kalitesi ayarlanabilir, son kare yayımcısı.
		- Kullanım: Gateway ile `/camera/*` altında stream ve snapshot uçları (modül README’sine bakın).
		- Sınırlar: PiCamera2 sürücü/firmware gereksinimleri; düşük ışıkta hız/kalite ayarı gerekebilir.
	- VLM Bridge (modules/vlm_bridge)
		- Kapsam: OpenCV tabanlı yüz algılama/tanıma ve takip; dış işlemci sonuçlarını Pi5’e HTTP ile yollar.
		- API: `POST /vlm/track { head_tilt, head_pan, drive? }` → Arduino “track” komutuna köprü.
		- Not: `POST /vlm/mode` ile objects/people/ocr/depth gibi yetenekler tek tek açılıp kapatılabilir.
		- Sınırlar: Ağ gecikmesi; kontrol döngüsünde stabilite için sınırlamalar (slew/ölü bant) önerilir.
	- Konuşma Tanıma (modules/speech)
		- Kapsam: SpeechRecognition ile çok dilli Google STT; I2S mikrofon; stereo’da DoA hesaplar.
		- API: `/speech/start`, `/speech/stop`, `/speech/last`, `/speech/direction`, `/speech/track/*`
		- Veri akışı: ALSA → çerçeveler → SpeechRecognition / Google STT → metin; stereo ise GCC-PHAT → açı.
		- Sınırlar: DoA için stereo şart.
	- Telemetri & Durum (modules/telemetry, modules/state_manager)
		- Telemetry: `/telemetry/metrics` Prometheus; `/telemetry/events` ham olay yayımı.
		- State Manager: `/state/get`, `/state/set/emotions`, `/state/set/<key>` — global durum ve duygular için kalıcı anahtar/değer desteği.

- İfade/Arayüz
	- Speak (TTS) (modules/speak)
		- Kapsam: pyttsx3 veya Piper ile offline TTS; base64 WAV oynatma; ALSA çıkış cihazı seçimi.
		- API: `/speak/say { text, engine? }`, `/speak/play { data: base64-wav }`
		- Sınırlar: Piper için model/binary gerekir; ses cihazı eşleşmesi (ALSA) şarttır.
	- NeoPixel (modules/neopixel)
		- Kapsam: Donanım/simülatör otomatik; ileri seviye animasyonlar ve duygusal renk paletleri.
		- API: `/neopixel/fill`, `/neopixel/effect`, `/neopixel/emote`, `/neopixel/animate`
		- Sınırlar: LED sayısı ve hız config’den alınır; ağır animasyonlarda CPU yükü artabilir.

		# NeoPixel API (user-facing notes)
		- `GET /neopixel/animations` — returns a curated, human-friendly list of available animations. Use `?show_all=true` to see every registered animation key.
		- `GET /neopixel/emotions` — returns a simple list of emotion names (e.g. `admiration`, `joy`). Color codes are intentionally hidden from the UI; the service will pick a random palette variant when an emotion is triggered.
		- `POST /neopixel/animate` — accepts a JSON body with fields `name` (animation key), optional `color` ("R,G,B" or "#RRGGBB") or `r,g,b` channels, optional `emotions` (list) and `iterations`.
		  Example body: `{ "name": "WAVE", "color": "0,255,255", "iterations": 2 }`
		- `POST /neopixel/emote` — convenience endpoint. Accepts `emotion` (single name), `emotions` (list) or `text`. If an `emotion` is provided, the server will randomly select one of the palette variants for that emotion and display it (no palette codes are returned in the API response for UI simplicity).
		- Behavior: The driver will attempt to play animations using the native Pi driver when available (hardware-accelerated). If the native driver does not support an animation name the server will fall back to Python implementations.
	- Interactions (modules/interactions)
		- Kapsam: Kurallara göre NeoPixel efektleri tetikleme; CPU sıcaklık/yük, ağ burst, olaylar.
		- API: `/interactions/event`, `/interactions/effect`, `/interactions/base`, `/interactions/state`
		- Sınırlar: NeoPixel servisi yoksa no-op; gelişmiş segment/mask için API genişlemesi önerilir.
	- Animasyon (modules/animate)
		- Kapsam: YAML tanımlı servo poz sekansları; `xAnimateService.run('name')` ile tetikleme.
		- Şema örneği: `name`, `loop`, `steps[{ pose[], duration_ms|hold_ms }]`.
	- Bildirimler (modules/notifier)
		- Kapsam: Telegram/Discord köprüleri; test ucu ve basit metin gönderimi.
		- API: `/notify/telegram`, `/notify/discord`, `/notify/test`

- Zeka
	- LLM (Ollama) (modules/ollama)
		- Kapsam: Kişilik (persona) yönetimi ile LLM sohbet; modül içi persona klasör yapısı.
		- API: `/ollama/chat`, `/ollama/persona`, `/ollama/personas`, `/ollama/persona/select`
		- Veri akışı: Speech → Ollama.chat → Speak; Interactions/NeoPixel opsiyonel duygusal tepki verebilir.


## Hızlı Başlangıç

1) Bağımlılıkları yükle (opsiyonel kolay kurulum scriptleri):
	 - Windows PowerShell veya Linux’ta kök dizinden çalıştırın: `install_all_requirements.py` ya da `install_all_requirements.sh`
	 - Donanım/harici yazılımlar (piper, ffmpeg, avrdude vb.) için ilgili modül README’lerine bakın

2) Gateway’i başlat (önerilen üretim modu):
	 - `python run_robot.py`
	 - Varsayılan adres: `http://localhost:8080`
	 - Örnek sağlık kontrolleri: `/neopixel/healthz`, `/speech/healthz`, `/arduino/healthz`

3) Tek modül olarak çalıştırma (geliştirme/test):
	 - Örnek: NeoPixel Servis → `uvicorn modules.visual_output.neopixel.xNeopixelService:create_app --factory --host 0.0.0.0 --port 8092`
	 - Örnek: Speech API → `python -m modules.voice.speech.xSpeechService --api`

Notlar:
- RPi5 üzerinde ALSA ses cihazları ve I2S mikrofon kart(lar)ı için sistem düzeyinde ayarlar gerekebilir (modül README’lerine bakın).
- Arduino bağlantısı için port otomatik bulunur; gerekirse `ARDUINO_PORT` ve `ARDUINO_BAUD` ile override.


## Docker ile Çalıştırma

Kök dizinde hazır Docker dosyaları bulunur:
- `Dockerfile`
- `docker-compose.yml`
- `modules/gateway/config/config.docker.yml`
- `docker-compose.full.yml`
- `modules/gateway/config/config.docker.full.yml`
- `docker-compose.rpi.yml`
- `modules/gateway/config/config.docker.rpi.yml`

1) Build + başlat:
	- `docker compose up --build -d`
2) Logları izle:
	- `docker compose logs -f sentrybot-gateway`
3) Durdur:
	- `docker compose down`

Varsayılan Docker konfigürasyonu donanım bağımlı modülleri kapalı getirir ve API çekirdeğini başlatır.

Full profil (tüm modüller include, autostart kapalı):
- `docker compose -f docker-compose.yml -f docker-compose.full.yml up --build -d`

Raspberry Pi 5 + Arduino profili (donanım modülleri açık):
- `docker compose -f docker-compose.yml -f docker-compose.rpi.yml up --build -d`

- Sağlık kontrolü: `http://localhost:8080/healthz`
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- Modül include ayarlarını değiştirmek için `modules/gateway/config/config.docker.yml`, `modules/gateway/config/config.docker.full.yml` veya `modules/gateway/config/config.docker.rpi.yml` dosyalarını düzenleyin.
- Alternatif bir gateway config kullanmak için `GATEWAY_CONFIG` environment variable’ını override edin.
- Raspberry Pi/Linux cihaz eşlemeleri `docker-compose.rpi.yml` içinde hazırdır.


## Konfigürasyon

- Gateway yapılandırması: `modules/gateway/config/config.yml`
	- `server.host / server.port` (varsayılan: 0.0.0.0:8080)
	- `include.<module>` anahtarları ile modülleri aç/kapat
- Modül yapılandırmaları: Her modül altında `config/config.yml`
	- Örnek env değişkenleri: `ARDUINO_PORT`, `ARDUINO_BAUD`, `NEO_DEVICE`, `NEO_NUM_LEDS` …
- Canlı düzenleme: Config Center UI → `/config/ui` (Gateway açıkken)


## API Haritası (Özet)

Gateway açıkken tüm modül uçları tek porttadır. Genel sağlık uçları: `/<modül>/healthz`.

- Arduino Seri: `/arduino/*` – hello, request/send, telemetry
- VLM Bridge: `/vlm/track` – dış işlemci komut köprüsü
- Kamera: `/camera/*` – API/stream
- NeoPixel: `/neopixel/*` – efektler, duygular, animasyon
- Interactions: `/interactions/*` – kural motoru, event tetikleme
- Speak (TTS): `/speak/*` – say/play
- Speech (ASR/DoA): `/speech/*` – tanıma başlat/durdur, yön, takip
- Ollama: `/ollama/*` – chat, persona yönetimi
- PiServo: `/piservo/*` – kulak jestleri
- Telemetry: `/telemetry/*` – Prometheus `/metrics`, event
- Diagnostics: `/diagnostics/*` – self-check ve rapor
- State Manager: `/state/*` – global durum/emotions
- Scheduler: `/scheduler/*` – iş listesi
- Scheduler: `/scheduler/*` – iş listesi, dinamik görev ekleme/silme ve sonuç takibi
- Notifier: `/notify/*` – Telegram/Discord köprüleri
- Config Center: `/config/*` – YAML okuma/düzenleme, UI

Detaylar ve örnek istekler her modülün README’sinde mevcuttur.


## Donanım Özeti ve Notlar

- RPi5 ana bilgisayar, Arduino (ör. Mega) USB ile bağlı
- I2S mikrofon(lar) (stereo önerilir) → Offline ASR ve DoA için
- MAX98357A I2S DAC → hoparlör çıkışı (Speak modülü)
- WS2812/NeoPixel şerit + Jewel (7) + Stick (16) varsayılan haritalama
- İki mini servo (kulaklar) → PiServo
- Kamera: PiCamera2 veya USB Webcam (auto seçimi desteklenir)
- Görüntü işleme ağır ise bir PC’ye stream + VLM Bridge ile komut köprüleme


## Arduino Firmware Özeti ve Donanım Detayları

Arduino tarafı gerçek zamanlı I/O ve hareket kontrolünden sorumludur. NDJSON tabanlı satır‑satır komutlarla çalışır.

- I2C Servo Sürüş (PCA9685)
	- Frekans: 50 Hz. Kanallar: 0–15 (konfigürasyonla atanır).
	- Konfig makroları (örnek): `SERVO_USE_PCA9685=1`, `PCA9685_ADDR=0x40`, `SERVO_MIN_US=500`, `SERVO_MAX_US=2500`.
	- detach/reattach ve tam‑kapat (full‑off) kenar durumları ele alınmıştır.
- Lazerler (iki adet X‑cross)
	- Firmware komutu: `{ "cmd":"laser", "id":1|2, "on":true }`, `{ "cmd":"laser", "both":true, "on":true }`, `{ "cmd":"laser", "on":false }`.
	- Pi tarafı API: `/arduino/laser/one/{1|2}`, `/arduino/laser/both`, `/arduino/laser/off` (gateway altında).
- LCD 16×1 ekranlar
	- Donanımsal olarak 8×2 gibi adreslenir; 16 karakterlik satırlar 8+8 olarak yazdırılır (kutucuk sorunu çözülür).
- Ultrasonik, IMU, PID, Stepper
	- Komut yüzeyi: `set_servo`, `set_pose(duration)`, `leg_ik`, `stepper(pos/vel/cfg)`, `home/zero`, `pid on/off`, `stand/sit`, `imu_read/cal`, `eeprom save/load`, `tune`, `policy`, `track`, `telemetry_*`, `get_state`, `estop`.

Donanım bağlamaya dair pratik notlar:
- Pi↔Arduino seviye dönüştürücü yönü doğru olmalı (Pi→LV, Arduino→HV hatları). I2C için pull‑up’lar tek tarafta yeterlidir.
- PCA9685 beslemesi ve servo güç hattı kalın iletken ve ortak GND ile bağlanmalıdır.


## Hızlı API Örnekleri

Gateway çalışıyorsa tüm uçlar tek porttadır. Aşağıdaki istekler örnektir:

- Lazerleri kontrol et (Arduino üzerinden)
	- Tek lazer: POST `/arduino/laser/one/1`
	- Her ikisi: POST `/arduino/laser/both`
	- Kapat: POST `/arduino/laser/off`

- NeoPixel duygusal renk gösterimi
	- POST `/neopixel/emote` body: `{ "text": "joy curiosity", "duration": 0.25 }`

- Görüntü işleme köprüsü (dış istemci → servo)
	- POST `/vlm/track` body: `{ "head_pan": 20, "head_tilt": -5 }`

- Konuşma
	- ASR başlat/durdur: `/speech/start`, `/speech/stop`
	- TTS: `/speak/say` body: `{ "text": "Merhaba!" }`
	## Modüller (Tek Tek)

	- **agent_core**: 3-katmanlı LLM tabanlı otonom zekâ (Router, Sub-agents, Persona) ve epizodik bellek yönetimi.
	- **ai_provider**: (eski adıyla ollama) LLM sohbet ve persona yönetimi; LLM endpointleri.
	- **arduino_serial**: Arduino Mega ile NDJSON seri köprü. Servo, stepper, imu, telemetry ve lazer kontrolü (esp_link'i içerir).
	- **autonomy**: Live Mode. Duygu durum yönetimi (MoodManager), davranış döngüsü, VLM algı birleştirme ve otonom tepki/sahne yöneticisi.
	- **calibration**: Servo, Kamera ve Ses kalibrasyon yardımcıları.
	- **camera**: PiCamera2/OpenCV backend ile görüntü yakalama ve yayın.
	- **cognitive_memory**: (eski adıyla social_db) Kişiler, ilişkiler, görülme kayıtları, sohbet geçmişi ve anıları tek merkezde toplayan birleşik SQLite bellek.
	- **common**: Ortak yardımcılar, paylaşılan duygu/ifade (emotion) sözlüğü (`emotion_vocab.py`).
	- **expression**: Semantik ifade motoru. Sistem olaylarını senkronize animasyon, renk ve oled yüz ifadelerine dönüştürür (interactions'ı içerir).
	- **gateway**: Ana giriş noktası. Tüm modül router'larını tek bir FastAPI uygulamasında toplar.
	- **hardware**: RPi5 sağlık/sistem, I2C tarama, GPIO özet uyarıları.
	- **motion**: (eski animate ve piservo) YAML tabanlı servo sekansları ve kulak jestleri (I2C ve PWM).
	- **mutagen**: Mutagen CLI üzerinden dosya senkron yönetimi (cihaz ↔ robot).
	- **ota**: Over-the-air güncelleme altyapısı (örn: uzaktan Arduino firmware dağıtımı).
	- **runtime_console**: Logosuz, panel tabanlı sade terminal arayüzü / TUI görünümü (logwrapper'ı içerir).
	- **scheduler**: Dinamik zamanlanmış periyodik görevler ve HTTP ping işleri.
	- **system_control**: (eski state_manager, diagnostics, telemetry, config_center, notifier) Global sistem durumu, donanım/yazılım sağlık kontrolü, telemetri verileri ve yapılandırma yönetimi.
	- **visual_output**: (eski neopixel ve oled_faces) WS2812 LED animasyonları, renk paletleri ve SSD1306 prosedürel göz ifadeleri.
	- **vlm_bridge**: Yüz algılama/tanıma (OpenCV) ve Vision Language Model isteklerini işleyip donanım komutlarına dönüştürme.
	- **voice**: (eski speech, speak, wakeword) SpeechRecognition ASR, ses yönü, TTS ve OpenWakeWord dinleyicisi.


	## Tipik Senaryolar

	- Hedefe Bak (Görüntü → Servo): Dış istemci görüntüyü işler → `/vlm/track` ile açı gönderir → Arduino (PCA9685) pan/tilt yapar.
	- Konuş ve Yanıtla: `/speech/start` ile dinle → metni `/ollama/chat`’e gönder → yanıtı `/speak/say` ile seslendir → Interactions NeoPixel efekt tetikler.
	- Duruma Göre Işıklar: Interactions CPU ısısı/yük, ağ burst ve olay akışını izler → NeoPixel’de base/transient animasyonlar oynatır.
	- Lazer/LCD/Ultrasonik: `/arduino/laser/*` ile lazerleri tekli/ikili; ultrasonik ölçümleri LCD’de 16×1 uyumlu göster.


## Geliştirici Otomasyonları (GitHub Actions)

Repo, modül merkezli çalışma akışını destekleyen etiketleme ve yardımcı iş akışlarıyla gelir.

- PR Etiketleyici (otomatik)
	- Değişen dosya yollarından `modules/<ad>/...` ile modül adı bulunur ve `module: <ad>` etiketi eklenir.
	- Branch adına göre tür etiketi: `type: feature` (feat/*, feature-*) ve hedef branch etiketi: `target: dev`.
- Etiket Eşitleme
	- Depodaki etiketleri bir YAML tanımıyla senkron tutar (yeni modüllere renkli etiketler).
- Açık PR’ları Geriye Dönük Etiketleme
	- Actions → “Relabel Open PRs” → Run workflow. Değişen dosyalardan modül tespit eder; eksik etiket varsa oluşturur ve uygular.

Önerilen ek iş akışları (isteğe bağlı):
- Lint/Test (Ruff/Black/Pytest) — değişen modüllerle sınırlı koşum
- Arduino derleme kontrolü (`arduino-cli`) — firmware bütünlüğü
- actionlint/yamllint — workflow sağlığı
- pip‑audit/safety ve gitleaks — güvenlik taramaları


## Geliştirme Rehberi (DryCode)

- Her modül tek sorumluluk ve küçük bileşenlerden oluşur
- `x<ModuleName>Service.py` servis başlatıcıdır (app fabrikası + config yükleyici)
- Dosya yapısı örneği ve kurallar: `.github/copilot-instructions.md`
- Konfig değerleri yalnızca YAML’dan okunur; kodda hardcode edilmez
- Test edilebilirlik ve loglama önceliklidir


## Modüller ve Belgeler

- Gateway: modules/gateway/README.md
- Arduino Serial: modules/arduino_serial/README.md
- Hardware: modules/hardware/README.md
- Camera: modules/camera/README.md
- VLM Bridge: modules/vlm_bridge/README.md
- NeoPixel: modules/neopixel/README.md
- Interactions: modules/interactions/README.md
- Speak (TTS): modules/speak/README.md
- Speech (ASR/DoA): modules/speech/README.md
- PiServo: modules/piservo/README.md
- Animate: modules/animate/README.md
- State Manager: modules/state_manager/README.md
- Telemetry: modules/telemetry/README.md
- Scheduler: modules/scheduler/README.md
- Diagnostics: modules/diagnostics/README.md
- Notifier: modules/notifier/README.md
- OTA: modules/ota/README.md
- Mutagen: modules/mutagen/README.md
- Config Center: modules/config_center/README.md
- Log Wrapper: modules/logwrapper/README.md
- LLM (Ollama): modules/ollama/README.md


## Katkıda Bulunma

PR’ler ve öneriler memnuniyetle karşılanır. Yeni modül eklerken DryCode kurallarına ve modül şablonuna uyun. Küçük, okunabilir, test edilebilir değişiklikler tercih edilir.


## Sponsor ve Destek

Projeyi surdurulebilir sekilde gelistirmemize destek olmak isterseniz GitHub Sponsors uzerinden sponsor olabilirsiniz:

- https://github.com/sponsors/WhoIsMrSentry

Destek detaylari icin: `.github/SUPPORT.md`


## Lisans

SentryBOT NC-Atif 1.0 (Ticari Kullanim Yasak, Atif Zorunlu) — ayrintilar icin `LICENSE` dosyasina bakin.
