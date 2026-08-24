# Voice - Speak (TTS)

SentryBOT'un konuşma çıkış modülüdür. Metni temizler, seçilen TTS motoruyla sentezler, sesi oynatır ve ifade katmanına konuşma başlangıç/bitiş olayları gönderir.

## Ana Yetenekler

- Çoklu TTS motoru: `piper` (yerel), `xtts` / `remote` (HTTP backend), `dummy` (test) — eski `pyttsx3` motoru kaldırıldı
- Senkron konuşma ve parçalara bölünmüş streaming konuşma
- Base64 WAV oynatma (remote TTS sonrası)
- Ton/eğilim eşleme: `joy`, `calm`, `tired`, `fear`, `anger`, `sadness` gibi preset'ler (prosody injection)
- Latency trace üretme (perf analizi)
- Konuşma sırasında expression/event bildirimi (`speak.started`, `speak.finished`)

## Mimari (Güncel: 2026-08-25)

- Giriş noktası: `xSpeakService.py` → `SpeakService`
- **Router**: `api/router.py`
- **TTS Core**: `services/tts.py` → `TTSConfig` dataclass + `TextToSpeech` facade
  - Backend'ler (`TTSBackend` türevleri): `UnavailableBackend`, `DummyBackend`, `PiperBackend` (`services/tts.py`); `XTTSHttpBackend`, `RemoteTTSHttpBackend` (`services/tts_remote_backends.py`)
  - Kalıcı Piper model yönetimi: `services/tts_piper_model.py` → `PersistentPiperModel` (model cache, streaming synth)
- **Oynatıcı**: `services/player.py` → `AudioPlayer` (ALSA/PulseAudio, chunked playback)
- **Yardımcılar**: 
  - `services/pcm.py` → PCM utils (resample, convert)
  - `services/lang_detect.py` → `LanguageDetector` (TR/EN heuristic, Piper voice lock)

## Bağımlılıklar (Güncel Modül Yolları)

- `system_control/config_center` → Merkezi `config/agent.yaml` içindeki `speak` bölümünü yükleme
- `common.latency_trace` → Gecikme izleri
- `runtime_console/logwrapper` → Merkezi logging
- `expression` → `expression_base_url` üzerinden `speak.started/finished` olayları (semantic state sync)
- `voice/speech` → Barge-in akışı (`speech` modülü `speak.stop` çağırır)
- `autonomy` → LLM yanıtlarını seslendirmek için ana consumer

## API (Gateway altında `/speak/*`)

- `GET /speak/status`
- `GET /speak/latency/latest` / `GET /speak/latency/{trace_id}`
- `POST /speak/stop` - Aktif konuşmayı durdur (barge-in)
- `POST /speak/say` - Senkron TTS + oynatma
  - Body: `{text, engine?, tone?, language?, streaming?}`
- `POST /speak/say_stream` - Streaming TTS (chunked response)
- `GET /speak/jobs/{job_id}` - Streaming job durumu
- `POST /speak/play` - Base64 WAV oynatma (remote TTS sonrası)

## Konfigürasyon

Merkezi `config/agent.yaml` → `speak` section + modül-içi `config/config.yml` (merge):

- `server.*` - API host/port
- `audio_out.*` - ALSA device, sample_rate, channels
- `tts.engine` - `piper|xtts|dummy` (`tts.remote.enabled: true` ile HTTP remote backend)
- `tts.model_path`, `tts.config_path` - Aktif Piper modeli (repo-relative), `tts.speaker` (not: `speaker_id` değil)
- `tts.piper.*` - `voice`, `auto_language`, `prefer_text_language`, `lock_session_language`, `fallback_engine`, `preload_voices`, `voices.*` (voice başına model_path/config_path)
- `tts.language_voices` - Dil → Piper voice eşlemesi (örn. `tr: tr`, `en: glados`)
- `tts.xtts.*` - Remote endpoint, timeout, speaker_wav, language
- `tts.naturalness.*`, `tts.stream_max_chunk_chars`, `tts.allow_dummy_fallback`
- `liveliness.*` - `expression_base_url`, `event_timeout_s` (event bildirimi)

`config_loader.py` kısa uyumluluk anahtarlarını normalize eder (`engine` → `tts.engine`) ve `piper` model yollarını depo köküne göre mutlaklaştırır.

**Prosody notu:** Ton preset'lerinden gelen prosody injection artık ayrı bir modülle değil, `xSpeakService` içinde tone'un `rate` değerinin Piper `length_scale`'ine dönüştürülmesiyle yapılır (`length_scale = 170 / rate`, sınırlı aralıkta).

## İlişkiler

- `autonomy` tarafından LLM yanıtlarını seslendirmek için kullanılır (`POST /speak/say`)
- `voice/speech` modülünün barge-in akışında kesilebilir (`POST /speak/stop`)
- `expression` semantic state ile olay bazlı senkronize olur (`speak.started` → listening mode, `speak.finished` → baseline)

## Bilinen Sorunlar

1. **XTTS Remote Engine** - `services/tts.py` içinde `XTTSRemoteEngine` var ama `config.yaml`'de `tts.xtts.endpoint` gerekli. Pi'de ağır, PC'de kullanılmalı.
2. **Dummy Engine** - Testlerde `dummy` engine `ALLOW_DUMMY_TTS=1` env ile aktif edilmeli, aksi halde `unavailable` döner.
3. **Prosody Injection** - Sadece `piper` motorunda çalışır (`length_scale`, `noise_scale`). `pyttsx3`/`xtts` için `rate`/`volume`/`pitch` ayrı map gerektirir.