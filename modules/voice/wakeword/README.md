# Voice - Wakeword

SentryBOT'un düşük güçlü "her zaman dinle" katmanıdır. Wakeword algılandığında konuşma tanımayı açar, barge-in uygular ve olayları diğer modüllere iletir.

## Sorumluluklar

- Sürekli wakeword dinleme (arka plan, düşük CPU)
- Algı sonrası sınırlı STT penceresi açma
- TTS/agent için süreç içi barge-in (`speak.stop()`, `agent_core/speech/interrupt`)
- `expression/interactions` ve `visual_output/neopixel` olay tetikleme
- OpenWakeWord motor desteği (config'de `engine: openwakeword | vosk` seçeneği durur; Vosk fallback hâlâ mevcuttur)

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xWakewordService.py` → `WakewordService`
- **OpenWakeWord Runner**: `services/openwakeword_runner.py` → `OpenWakeWordRunner` (tflite/onnx model, streaming inference)
- **Kalibrasyon**: `services/openwakeword_calibration.py` → `OpenWakewordCalibrationMixin` (threshold auto-calibration)
- **Model Varlıkları**: `services/openwakeword_assets.py` (pretrained model kataloğu, indirme ve path çözümleme)
- **Wakeword Detector**: `services/wakeword_detector.py` → `WakewordDetector` (event orchestration)
- **Aksiyon Orkestrasyonu**: `WakewordActions` (Gateway `_wire_wakeword_interactions` ile in-process servis çağrıları)
- **Ses Yakalama**: **ORTAK** - `voice/speech/services/audio_capture` (paylaşımlı capture, ALSA çakışmasız) - `modules/voice/audio_router.py` üzerinden yönlendirilir

## API (Gateway altında `/wakeword/*`)

- `GET /wakeword/healthz` / `/wakeword/status`
- `POST /wakeword/start` - Dinleme başlat
- `POST /wakeword/stop` - Dinleme durdur

## Akış

1. Wakeword algılanır (`hey_mycroft`, `ok_nabu`, custom)
2. `WakewordActions.interrupt_robot_speech()` çağrılır → `speak.stop()` + `agent_core/speech/interrupt`
3. `speech/start` tetiklenir (STT penceresi açılır)
4. `listen_window_sec` boyunca STT sonucu beklenir
5. Final sonuç gelince `speech/stop` ve `expression/interactions/event` gönderilir
6. `visual_output/neopixel` → `companion_wake` mode tetiklenir

## Konfigürasyon

Merkezi `config/agent.yaml` → `wakeword` section + modül-içi `config/config.yml` (merge):

- `wakeword.engine`: `openwakeword` (veya `vosk` fallback)
- `openwakeword.pretrained_models` - Yerleşik model adları (ilk çalıştırmada otomatik indirilir)
- `openwakeword.verifier_path` - Kişiye özel verifier (opsiyonel)
- `openwakeword.input_channels` - Runner giriş kanal sayısı (verilmezse `audio.channels` enjekte edilir)
- `openwakeword.auto_calibration.*` - Otomatik eşik kalibrasyonu (duration_sec, percentile, min/max_threshold)
- `actions.*_url` - `speech`, `speak`, `agent_core`, `interactions`, `neopixel` gateway URL'leri
- `listen_window_sec` - STT dinleme penceresi (default 5s)
- `recognition.vad` - Voice Activity Detection ayarları
- `openwakeword.threshold` - OpenWakeWord algı eşiği (`sensitivity` yerine)
- `wakeword.trigger_on_partial` / `wakeword.cooldown_sec` - Kısmi sonuçla tetikleme ve tekrar tetiklenme bekleme süresi

## İlişkiler (Güncel Modül Yolları)

- `voice/speech` → **ORTAK AUDIO CAPTURE** (tek I2S stream, multi-consumer) - `modules/voice/audio_router.py` mevcut
- `expression/interactions` → Wakeword olayları (`wakeword.detected` event)
- `gateway` → `_wire_wakeword_interactions` kablolaması (in-process service calls)
- `visual_output/neopixel` → `companion_wake` mode (ExpressionArbiter lease)
- `voice/speak` → Barge-in (`speak.stop()`)
- `agent_core` → Agent interrupt (`POST /agent/speech/interrupt`)

## Bilinen Sorunlar (KRİTİK)

1. **Audio Device Multiplexer ✅ ÇÖZÜLDÜ** - `voice/speech` (Vosk) ve `voice/wakeword` (OpenWakeWord) aynı I2S cihazını paylaşıyor; `modules/voice/audio_router.py` (MEVCUT) ile:
   - Tek `AudioCapture` singleton
   - Frame publisher → multiple subscribers (VoskRecognizer, OpenWakeWordRunner)
   - VAD paylaşımlı

2. **Gateway Wire Bypass** - `_wire_wakeword_interactions` in-process call yapıyor, event bus kullanmıyor. Testlerde mock zor.

3. **Verifier Yükleme** - `verifier_path` verildiğinde model yükleme hata veriyorsa sessizce fallback yapıyor (loglaması zayıf).