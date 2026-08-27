# Voice - Speech (ASR/DoA)

SentryBOT'un konuşma giriş modülüdür. Mikrofon akışını alır, SpeechRecognition ile Google çoklu dil STT çalıştırır, ses yönünü hesaplar ve gerektiğinde pan hareketini tetikler.

## Ana Yetenekler

- Ses yakalama ve arka plan dinleme (I2S, ALSA)
- SpeechRecognition çok dilli STT (çevrimiçi Google Multi-language STT)
- Wakeword algılama ve barge-in (OpenWakeWord entegrasyonu)
- Ses yönü kestirimi (DoA - GCC-PHAT, stereo mic gerekli)
- Pan takibi: **HeadControlArbiter** (priority lease), fallback Arduino servo komutu
- STT olaylarını `autonomy`, `expression/interactions`, `visual_output/oled_faces` tarafına iletme

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xSpeechService.py` → `SpeechService`
- **Router**: `api/router.py`
- **Ses Yakalama**: `services/audio_capture.py` → `AudioCapture`, `CaptureConfig`, `FramePublisher`
- **Tanıma**: 
  - `services/recognizer.py` → `SpeechRecognizer` (SpeechRecognition)
  - `services/stt_language.py` → `STTLanguageResolver` (TR/EN auto-detect, Piper voice lock)
  - `services/online_stt.py` → Google Speech Recognition multi-language
- **Yön ve Takip**: 
  - `services/direction.py` → `DoAEstimator` (GCC-PHAT, stereo frame processing)
  - `services/pan_tilt.py` → `PanTiltTracker` (head arbiter entegrasyonu)
- **Ses Ön İşleme**: `services/audio_filters.py` (downmix/gain PCM filtreleri)
- **Ses Kaynağı Takibi**: `services/sound_tracking.py` → `SpeechSoundTrackingMixin`

## Bağımlılıklar (Güncel Modül Yolları)

- `system_control/config_center` → Merkezi `config/agent.yaml` yükleme (speech section)
- `autonomy` → Final metin ve etkileşim bildirimi (speech event)
- `expression/interactions` → Konuşma başlangıç/bitiş olayları (event bus)
- `voice/speak` → Wakeword barge-in sırasında aktif konuşmayı kesme (`speak.stop`)
- `arduino_serial/contract` → Servo komutu üretme (fallback)
- `gateway/url` → Tek-port URL çözümleme
- `vlm_bridge` → `HeadControlArbiter` (head tracking priority lease)
- `visual_output/oled_faces` → STT metni altyazı için (`/oled_faces/stt_text`)

## API (Gateway altında `/speech/*`)

- `GET /speech/status`
- `POST /speech/start` - Dinleme başlat
- `POST /speech/stop` - Dinleme durdur
- `GET /speech/last` - Son tanınan metin
- `GET /speech/direction` - Son ses yönü (derece)
- `POST /speech/track/start` - Pan takibi başlat (DoA → head)
- `POST /speech/track/stop` - Pan takibi durdur
- `GET /speech/track/status`
- `POST /speech/stt/suppress` - STT geçici bastır (TTS sırasında)

## Olay Akışı

1. **Final STT çıktısı** → `autonomy` modülüne (`POST /autonomy/speech` veya event bus)
2. **Kısmi/final konuşma** → `expression/interactions` modülüne event olarak (`speech.started`, `speech.final`, `speech.partial`)
3. **Wakeword tespiti** → `voice/speak` stop, `agent_core/speech/interrupt`, opsiyonel `speech/start` yeniden (barge-in)
4. **Ses yönü (DoA)** → `HeadControlArbiter` lease isteği → `arduino_serial.track()` 
4. **STT metni** → `visual_output/oled_faces/stt_text` (altyazı)

## Konfigürasyon

Merkezi `config/agent.yaml` → `speech` section + modül-içi `config/config.yml` (merge):

- `server.*` - API host/port
- `audio.*` - I2S device, sample_rate, channels, format
- `recognition.*` - SpeechRecognition language, max_utterance
- `recognition.vad` - Voice Activity Detection ayarları (enabled, aggressiveness, hangover_ms)
- `direction.*` - DoA enabled, mic_distance, angle_smoothing
- `pan_tilt.*` - Track enabled, deadband, slew_rate, arbiter_priority

## Notlar

- Çevrimiçi Google Speech Recognition ile yüksek doğrulukta çok dilli konuşma tanıma yapılır.
- **Stereo I2S mic zorunlu** DoA için. Mono mic'de direction çalışmaz.
- **HeadControlArbiter** ile `vlm_bridge` (face track) ve `autonomy` (vision focus) paylaşımlı - priority lease sistemi.

## Bilinen Sorunlar

1. **Audio Device Multiplexer ✅ ÇÖZÜLDÜ** - `voice/wakeword` (OpenWakeWord) ve `voice/speech` (SpeechRecognition) `modules/voice/audio_router.py` ile tek capture üzerinden paylaşılır.
2. **PanTiltTracker ↔ HeadControlArbiter** - `pan_tilt.py` arbiter kullanıyor ama `direction.py` doğrudan `arduino.track()` çağırıyor (bypass riski).