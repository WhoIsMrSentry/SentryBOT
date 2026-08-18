# Speak

SentryBOT'un konuşma çıkış modülüdür. Metni temizler, seçilen TTS motoruyla sentezler, sesi oynatır ve ifade katmanına konuşma başlangıç/bitiş olayları gönderir.

## Ana Yetenekler

- Birden fazla TTS motoru: `pyttsx3`, `piper`, `xtts`, `dummy`
- Senkron konuşma ve parçalara bölünmüş streaming konuşma
- Base64 WAV oynatma
- Ton/eğilim eşleme: `joy`, `calm`, `tired`, `fear` gibi preset'ler
- Latency trace üretme
- Konuşma sırasında expression/event bildirimi

## Mimari

- Giriş noktası: `xSpeakService.py`
- Router: `api/router.py`
- TTS: `services/tts.py`
- Oynatıcı: `services/player.py`
- Yardımcılar: `services/pcm.py`, `services/lang_detect.py`

## Bağımlılıklar

- `config_center`: merkezi `config/agent.yaml` içindeki `speak` bölümünü yükleme
- `common.latency_trace`: gecikme izleri
- `logwrapper`: merkezi logging
- İfade katmanı: `expression_base_url` üzerinden `speak.started` ve `speak.finished` olayları

## API

Gateway altında `/speak/*` olarak yayınlanır.

- `GET /speak/status`
- `GET /speak/latency/latest`
- `GET /speak/latency/{trace_id}`
- `POST /speak/stop`
- `POST /speak/say`
- `POST /speak/say_stream`
- `GET /speak/jobs/{job_id}`
- `POST /speak/play`

## Konfigürasyon

Bu modül modül-içi `config/config.yml` yerine merkezi `config/agent.yaml` içindeki `speak` bölümünü okur.

- `server.*`
- `audio_out.*`
- `tts.*`
- `tts.piper.*`
- `tts.xtts.*`
- `liveliness.*`

`config_loader.py`, kısa uyumluluk anahtarlarını normalize eder ve `piper` model yollarını depo köküne göre mutlaklaştırır.

## İlişkiler

- `autonomy` tarafından LLM yanıtlarını seslendirmek için kullanılır
- `speech` modülünün barge-in akışında kesilebilir
- Görsel/ifade sistemiyle olay bazlı senkronize olur

## Notlar

Güncel kodda liveliness sinyali doğrudan `interactions` yerine yapılandırılmış bir `expression_base_url` üzerinden gönderilir. Ayrıca streaming konuşma, iş takibi ve latency endpoint'leri mevcut olduğundan README artık yalnızca temel `say` ve `play` yüzeyiyle sınırlı değildir.
