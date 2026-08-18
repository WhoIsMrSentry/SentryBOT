# Wakeword

SentryBOT'un düşük güçlü "her zaman dinle" katmanıdır. Wakeword algılandığında konuşma tanımayı açar, barge-in uygular ve olayları diğer modüllere iletir.

## Sorumluluklar

- Sürekli wakeword dinleme
- Algı sonrası sınırlı STT penceresi açma
- TTS/agent barge-in (`speak/stop`, `agent/speech/interrupt`)
- `interactions` ve NeoPixel olay tetikleme
- Vosk veya OpenWakeWord motor desteği

## Mimari

- Giriş noktası: `xWakewordService.py`
- Vosk yolu: `services/wakeword_detector.py`
- OpenWakeWord yolu: `services/openwakeword_runner.py` (`OpenWakewordRunner`)
- Aksiyon orkestrasyonu: `WakewordActions`
- Ses yakalama: `speech.services.audio_capture` (paylaşımlı capture)

Graph'ta `OpenWakewordRunner` yalnızca `WakewordService.__init__` tarafından başlatılır.

## API (Gateway altında `/wakeword/*`)

- `GET /wakeword/status`
- `POST /wakeword/start`
- `POST /wakeword/stop`

## Akış

1. Wakeword algılanır
2. `WakewordActions.interrupt_robot_speech()` çağrılır
3. `speech/start` tetiklenir
4. Kısa dinleme penceresi boyunca STT sonucu beklenir
5. Final sonuç gelince `speech/stop` ve `interactions/event` gönderilir

## Konfigürasyon

`modules/wakeword/config/config.yml`:
- `wakeword.engine`: `vosk` veya `openwakeword`
- `openwakeword.model_paths`, `verifier_path`
- `actions.*_url` (speech, speak, agent, interactions, neopixel)
- `listen_window_sec`, VAD ayarları

## Özel Verifier Eğitimi

`modules/wakeword/tools/train_verifier.py` ile kişiye özel OpenWakeWord verifier eğitilebilir.

## İlişkiler

- `speech`: STT pipeline paylaşımı
- `interactions`: wakeword olayları
- `gateway`: `_wire_wakeword_interactions` kablolaması
- Otonomlukta pasif bekleme → aktif dinleme geçiş kapısıdır
