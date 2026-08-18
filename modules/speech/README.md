# Speech

SentryBOT'un konuşma giriş modülüdür. Mikrofon akışını alır, yerel Vosk tabanlı STT çalıştırır, isteğe bağlı çok dilli çözümleme yapar, ses yönünü hesaplar ve gerektiğinde pan hareketini tetikler.

## Ana Yetenekler

- Ses yakalama ve arka plan dinleme
- Yerel Vosk tabanlı STT
- İsteğe bağlı çok dilli çözümleme ve çevrimiçi Google çoklu dil fallback'i
- Wakeword algılama ve barge-in
- Ses yönü kestirimi
- Pan takibi: önce head arbiter, olmazsa Arduino servo komutu fallback'i
- STT olaylarını `autonomy`, `interactions` ve OLED tarafına iletme

## Mimari

- Giriş noktası: `xSpeechService.py`
- Router: `api/router.py`
- Ses yakalama: `services/audio_capture.py`
- Tanıma: `services/recognizer.py`, `services/stt_language.py`, `services/online_stt.py`
- Yön ve takip: `services/direction.py`, `services/pan_tilt.py`
- Wakeword araçları: `services/wake_phrase.py`

## Bağımlılıklar

- `config_center`: merkezi `config/agent.yaml` yükleme
- `autonomy`: final metin ve etkileşim bildirimi
- `interactions`: konuşma başlangıç/bitiş olayları
- `speak`: wakeword barge-in sırasında aktif konuşmayı kesme
- `arduino_serial.contract`: servo komutu üretme
- `gateway.url`: tek-port URL çözümleme

## API

Gateway altında `/speech/*` olarak yayınlanır.

- `GET /speech/status`
- `POST /speech/start`
- `POST /speech/stop`
- `GET /speech/last`
- `GET /speech/direction`
- `POST /speech/track/start`
- `POST /speech/track/stop`
- `GET /speech/track/status`
- `POST /speech/stt/suppress`

## Olay Akışı

- Final STT çıktısı `autonomy` modülüne post edilir.
- Kısmi ve final konuşma olayları `interactions` modülüne event olarak gönderilir.
- Wakeword tespitinde `speak/stop`, `agent/speech/interrupt` ve gerekirse yeniden `speech/start` çağrılarıyla barge-in uygulanır.

## Konfigürasyon

Bu modül artık modül içi `config/config.yml` yerine merkezi `config/agent.yaml` içindeki `speech` bölümünü okur.

- `server.*`
- `audio.*`
- `recognition.*`
- `direction.*`
- `pan_tilt.*`

## Notlar

Kod artık yalnızca "tamamen offline" bir STT servisi değildir. Birincil akış yerel Vosk olsa da, `finalize_stt()` içinde uygun olduğunda çok dilli çevrimiçi çözümleme fallback'i de bulunur. Bu nedenle modül, otonom konuşma akışının hem algı hem de müdahale noktasıdır.
