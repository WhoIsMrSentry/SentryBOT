# SentryBOT – Modüler İki Ayaklı Yoldaş Robot Platformu

SentryBOT; Raspberry Pi 5 + Arduino tabanlı, modüler bir yoldaş robot ve servis mimarisidir. Tüm yetenekler bağımsız modüller hâlinde tasarlanır, tek bir Gateway üzerinden tek porttan API olarak sunulur. Donanım kontrolü Arduino ile yapılırken; konuşma tanıma/TTS, LED animasyonları, kamera ve LLM/RAG gibi fonksiyonlar Pi5 üzerinde mikro servisler olarak çalışır.

Ana hedefler:
- Basit, temiz, DryCode odaklı modüller
- Her modül hem kütüphane (import) hem servis (run) olarak çalışabilir
- Tüm konfigürasyonlar YAML dosyalarındadır ve gerektiğinde override edilebilir
- Donanım ağır işlerini Arduino üstlenir; görüntü işleme gibi pahalı işler gerekiyorsa dış istemcilere (PC) köprülenir


## Mimari Genel Bakış

- Donanım: Raspberry Pi 5 (ana bilgisayar) + Arduino (ör. Mega) kontrol kartı
- İletişim: Arduino ile NDJSON seri köprü; modüller arası HTTP (FastAPI)
- Gateway: Tüm modül router’larını tek FastAPI sürecinde birleştirir (varsayılan: 0.0.0.0:8080)
- Konfigürasyon: Her modül altında `config/config.yml`; merkezi düzenleme için Config Center
- Loglama: Merkezi log wrapper; dosya + bellek içi halka buffer

Başlatıcı akış (varsayılan): `run_robot.py` → Logları kurar → Gateway app’i oluşturur → Uvicorn ile tek porttan servis verir.


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
	- OTA (modules/ota)
		- Kapsam: avrdude ile Arduino firmware uzaktan yükleme; değişmeyen hash’ler yeniden yüklenmez.
		- API: `/ota/scan_once`, `/ota/upload`, `/ota/versions`
		- Sınırlar: avrdude ve doğru board/port ayarları gerekir.
	- Hardware (modules/hardware)
		- Kapsam: RPi5 sistem bilgisi, I2C tarama, GPIO özet uyarıları.
		- API: `/hardware/healthz`, `/hardware/system`, `/hardware/i2c/scan`
	- Mutagen (modules/mutagen)
		- Kapsam: Geliştirici cihaz ↔ robot dosya senkronu; OTA ile birlikte firmware dağıtımını kolaylaştırır.
		- API: `/mutagen/status`, `/mutagen/start`, `/mutagen/stop`
	- Teşhis & Zamanlama (modules/diagnostics, modules/scheduler)
		- Diagnostics API: `/diagnostics/run`, `/diagnostics/report` — modül sağlıklarını zincir hâlinde kontrol eder.
		- Scheduler API: `/scheduler/jobs` — basit async periyodik görevler, HTTP ping işleri.

- Duyular
	- Kamera (modules/camera)
		- Kapsam: PiCamera2/OpenCV backend; çözünürlük, FPS, JPEG kalitesi ayarlanabilir, son kare yayımcısı.
		- Kullanım: Gateway ile `/camera/*` altında stream ve snapshot uçları (modül README’sine bakın).
		- Sınırlar: PiCamera2 sürücü/firmware gereksinimleri; düşük ışıkta hız/kalite ayarı gerekebilir.
	- Vision Bridge (modules/vision_bridge)
		- Kapsam: Dış işlemci (PC) görsel analiz yapar; sonuç komutlarını Pi5’e HTTP ile yollar.
		- API: `POST /vision/track { head_tilt, head_pan, drive? }` → Arduino “track” komutuna köprü.
		- Sınırlar: Ağ gecikmesi; kontrol döngüsünde stabilite için sınırlamalar (slew/ölü bant) önerilir.
	- Konuşma Tanıma (modules/speech)
		- Kapsam: Vosk ile tamamen offline ASR; I2S mikrofon; opsiyonel WebRTC VAD; stereo’da DoA hesaplar.
		- API: `/speech/start`, `/speech/stop`, `/speech/last`, `/speech/direction`, `/speech/track/*`
		- Veri akışı: ALSA → çerçeveler → (opsiyonel VAD) → Vosk → metin; stereo ise GCC-PHAT → açı.
		- Sınırlar: DoA için stereo şart; model klasörlerinin doğru konfig edilmesi gerekir.
	- Telemetri & Durum (modules/telemetry, modules/state_manager)
		- Telemetry: `/telemetry/metrics` Prometheus; `/telemetry/events` ham olay yayımı.
		- State Manager: `/state/get`, `/state/set/emotions` — global durum ve duygular.

- İfade/Arayüz
	- Speak (TTS) (modules/speak)
		- Kapsam: pyttsx3 veya Piper ile offline TTS; base64 WAV oynatma; ALSA çıkış cihazı seçimi.
		- API: `/speak/say { text, engine? }`, `/speak/play { data: base64-wav }`
		- Sınırlar: Piper için model/binary gerekir; ses cihazı eşleşmesi (ALSA) şarttır.
	- NeoPixel (modules/neopixel)
		- Kapsam: Donanım/simülatör otomatik; ileri seviye animasyonlar ve duygusal renk paletleri.
		- API: `/neopixel/fill`, `/neopixel/effect`, `/neopixel/emote`, `/neopixel/animate`
		- Sınırlar: LED sayısı ve hız config’den alınır; ağır animasyonlarda CPU yükü artabilir.
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
	- RAG (Wiki) (modules/wiki_rag)
		- Kapsam: Yerel wiki içeriklerinden ön işleme + indeks ve sohbet; LlamaIndex + Ollama backend.
		- API: `/wiki_rag/preprocess`, `/wiki_rag/index/rebuild`, `/wiki_rag/chat`, `/wiki_rag/persona/select`
		- Sınırlar: Disk ve bellek maliyeti; Ollama sunucusu ve modeller kurulu olmalı.


## Hızlı Başlangıç

1) Bağımlılıkları yükle (opsiyonel kolay kurulum scriptleri):
	 - Windows PowerShell veya Linux’ta kök dizinden çalıştırın: `install_all_requirements.py` ya da `install_all_requirements.sh`
	 - Donanım/harici yazılımlar (piper, ffmpeg, avrdude vb.) için ilgili modül README’lerine bakın

2) Gateway’i başlat (önerilen üretim modu):
	 - `python run_robot.py`
	 - Varsayılan adres: `http://localhost:8080`
	 - Örnek sağlık kontrolleri: `/neopixel/healthz`, `/speech/healthz`, `/arduino/healthz`

3) Tek modül olarak çalıştırma (geliştirme/test):
	 - Örnek: NeoPixel Servis → `uvicorn modules.neopixel.xNeopixelService:create_app --factory --host 0.0.0.0 --port 8092`
	 - Örnek: Speech API → `python -m modules.speech.xSpeechService --api`

Notlar:
- RPi5 üzerinde ALSA ses cihazları ve I2S mikrofon kart(lar)ı için sistem düzeyinde ayarlar gerekebilir (modül README’lerine bakın).
- Arduino bağlantısı için port otomatik bulunur; gerekirse `ARDUINO_PORT` ve `ARDUINO_BAUD` ile override.


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
- Vision Bridge: `/vision/track` – dış işlemci komut köprüsü
- Kamera: `/camera/*` – API/stream
- NeoPixel: `/neopixel/*` – efektler, duygular, animasyon
- Interactions: `/interactions/*` – kural motoru, event tetikleme
- Speak (TTS): `/speak/*` – say/play
- Speech (ASR/DoA): `/speech/*` – tanıma başlat/durdur, yön, takip
- Ollama: `/ollama/*` – chat, persona yönetimi
- Wiki RAG: `/wiki_rag/*` – ön işleme, indeks, chat
- PiServo: `/piservo/*` – kulak jestleri
- OTA: `/ota/*` – tarama, upload, versiyonlar
- Mutagen: `/mutagen/*` – senkron yönetimi
- Hardware: `/hardware/*` – sistem/I2C/GPIO
- Telemetry: `/telemetry/*` – Prometheus `/metrics`, event
- Diagnostics: `/diagnostics/*` – self-check ve rapor
- State Manager: `/state/*` – global durum/emotions
- Scheduler: `/scheduler/*` – iş listesi
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
- Görüntü işleme ağır ise bir PC’ye stream + Vision Bridge ile komut köprüleme


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
- Vision Bridge: modules/vision_bridge/README.md
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
- Wiki RAG: modules/wiki_rag/README.md


## Katkıda Bulunma

PR’ler ve öneriler memnuniyetle karşılanır. Yeni modül eklerken DryCode kurallarına ve modül şablonuna uyun. Küçük, okunabilir, test edilebilir değişiklikler tercih edilir.


## Lisans

Apache 2.0 — ayrıntılar için `LICENSE` dosyasına bakın.
