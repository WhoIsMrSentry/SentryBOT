# SentryBOT – Modüler İki Ayaklı Yoldaş Robot Platformu

SentryBOT; Raspberry Pi 5 + Arduino tabanlı, modüler bir yoldaş robot ve servis mimarisidir. Tüm yetenekler bağımsız modüller hâlinde tasarlanır, tek bir Gateway üzerinden tek porttan API olarak sunulur. Donanım kontrolü Arduino ile yapılırken; konuşma tanıma/TTS, LED animasyonları, kamera ve LLM/RAG gibi fonksiyonlar Pi5 üzerinde mikro servisler olarak çalışır.

Ana hedefler:
- Basit, temiz, DryCode odaklı modüller
- Her modül hem kütüphane (import) hem servis (run) olarak çalışabilir
- Tüm konfigürasyonlar YAML dosyalarındadır ve gerektiğinde override edilebilir
- Donanım ağır işlerini Arduino üstlenir; görüntü işleme gibi pahalı işler gerekiyorsa dış istemcilere (PC) köprülenir


## Neler Yeni? (Öne Çıkan Son Geliştirmeler)

- Servo sürüşü I2C’ye taşındı (PCA9685, 50 Hz). Açı→mikrosaniye darbe haritalaması konfigüre edilebilir (min/max us).
- Çift “X‑cross” lazer eklendi: tekli ya da ikisi birden aç/kapa (firmware komut + Pi API).
- 16×1 I2C LCD’ler için 8×2 adresleme düzeltmesi: 16 karakter mesajlar 8+8’e bölünerek yazdırılır.
- **Duygu Motoru (Emotional Engine)**: Robotun iç durumu (Mutluluk, Enerji, Merak, Korku) davranışlarını ve NeoPixel ışıklarını otomatik olarak etkiler (örn: `joy` -> altın rengi nefes alma).
- **Tam Yapılandırılmış Çıktı (Structured JSON)**: Ollama artık tüm yanıtlarını düşünce (thoughts), vokal yanıt (text) ve fiziksel aksiyonlar (actions) içeren katı bir JSON formatında döner.
- **Sistem-Genel Modül Kontrolü**: Robot artık kendi modüllerini (notifier, camera, speech vb.) LLM kararlarıyla çalışma esnasında kapatıp açabilir.


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
	- POST `/vision/track` body: `{ "head_pan": 20, "head_tilt": -5 }`

- Konuşma
	- ASR başlat/durdur: `/speech/start`, `/speech/stop`
	- TTS: `/speak/say` body: `{ "text": "Merhaba!" }`


	## Modüller (Tek Tek)

	- animate
		- Amaç: YAML tabanlı servo animasyon sekansları; isimle tetiklenir.
		- Kullanım: `xAnimateService.run('sit')`; adımlar `pose[]` ve `duration_ms|hold_ms` içerir.
		- Config: `modules/animate/config/config.yml`

	- arduino_serial
		- Amaç: Arduino Mega ile NDJSON seri köprü; sürücü sınıfı + opsiyonel API.
		- Kabiliyet: servo/pose/stepper/imu/telemetry/estop + lazer (tekli/çift) kontrolü.
		- Uçlar: `/arduino/healthz`, `/arduino/request`, `/arduino/telemetry/start`, `/arduino/laser/*`.
		- Config: port AUTO, baudrate; env: `ARDUINO_PORT`, `ARDUINO_BAUD`.

	- calibration
		- Amaç: Servo/Kamera/Audio kalibrasyon yardımcıları.
		- Uçlar: `/calib/healthz`, `/calib/camera/checkerboard`, `/calib/servo/sweep`.

	- camera
		- Amaç: PiCamera2/OpenCV backend ile görüntü yakalama ve yayın.
		- Özellikler: çözünürlük/FPS/JPEG kalite; yayıncı son kareyi saklar.
		- Uçlar: `/camera/*` (gateway altında).

	- config_center
		- Amaç: Modül `config.yml` dosyalarını listele/düzenle; minimal UI.
		- Uçlar: `/config/healthz`, `/config/list`, `/config/get|raw|set`, `/config/scan`, `/config/ui`.

	- diagnostics
		- Amaç: Boot self‑check ve modül sağlık taraması.
		- Uçlar: `/diagnostics/healthz`, `/diagnostics/run`, `/diagnostics/report`.

	- gateway
		- Amaç: Ana giriş; tüm modül router’larını tek app’te toplar.
		- Uçlar: Tüm modüller tek portta; `/healthz`, `/status` özet; `include.*` yönetimi.

	- hardware
		- Amaç: RPi5 sağlık/sistem, I2C tarama, GPIO özet.
		- Uçlar: `/hardware/healthz`, `/hardware/system`, `/hardware/i2c/scan`, `/hardware/gpio/info`.

	- interactions
		- Amaç: Kural motoru; metrikler/olaylara göre NeoPixel efektleri.
		- Uçlar: `/interactions/event|effect|base|state`.

	- logwrapper
		- Amaç: Merkezi loglama; console + dönen dosya + bellek içi halka buffer.
		- Uçlar: Opsiyonel FastAPI router ile loglara erişim.

	- mutagen
		- Amaç: Mutagen CLI üzerinden dosya senkron yönetimi (cihaz ↔ robot).
		- Uçlar: `/mutagen/healthz|status|start|stop|rescan`.

	- neopixel
		- Amaç: WS2812 LED kontrolü; donanım/simülatör otomatik; zengin animasyonlar ve "emotions" paleti.
		- Uçlar: `/neopixel/healthz|clear|fill|effect|emote|emote_named|animate`.

	- notifier
		- Amaç: Telegram/Discord köprüleri.
		- Uçlar: `/notify/healthz`, `/notify/telegram`, `/notify/discord`, `/notify/test`.

	- ollama
		- Amaç: LLM sohbet/persona; persona klasör yapısıyla yönetim.
		- Uçlar: `/ollama/healthz|chat|persona(s)|persona/select|persona/create_from_url`.

	- ota
		- Amaç: Over‑the‑air güncelleme altyapısı (örn. Arduino firmware dağıtımı).

	- piservo
		- Amaç: Pi üzerinde kulak/ikincil servolar (pigpio) — jestler ve basit hareketler.
		- Uçlar: `/piservo/*` (kulak pozları ve jestler).

	- scheduler
		- Amaç: Zamanlanmış işler; basit periyodik görevler (ör. sağlık pingi).
		- Uçlar: `/scheduler/jobs` (liste/ekleme/çıkarma).

	- speak
		- Amaç: TTS (pyttsx3 veya Piper); base64 WAV oynatma; ALSA cihaz seçimi.
		- Uçlar: `/speak/say`, `/speak/play`.

	- speech
		- Amaç: Offline ASR (Vosk), I2S; stereo ise DoA ve takip.
		- Uçlar: `/speech/start|stop|last|direction|track/*`.

	- state_manager
		- Amaç: Global durum/emotions yönetimi.
		- Uçlar: `/state/get`, `/state/set/emotions`.

	- telemetry
		- Amaç: Telemetri; Prometheus `/metrics` ve olay yayımı.
		- Uçlar: `/telemetry/*`.

	- vision_bridge
		- Amaç: Dış görüntü işleme sonuçlarını Arduino komutlarına köprüler.
		- Uçlar: `/vision/*` (ör. `/vision/track` → Arduino "track").

	- wiki_rag
		- Amaç: Yerel bilgi depoları (wiki) üzerinden RAG; persona ile sohbet bağlamı.
		- Uçlar: `/wiki_rag/*` (preprocess, index/rebuild, chat, persona/select).


	## Tipik Senaryolar

	- Hedefe Bak (Görüntü → Servo): Dış istemci görüntüyü işler → `/vision/track` ile açı gönderir → Arduino (PCA9685) pan/tilt yapar.
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
