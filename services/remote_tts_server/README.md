# Remote TTS Server

PC tarafında çalışan SentryBOT TTS sunucusudur. Piper (yerel CLI) ve XTTS seslendirmesini robotun donanımından ayırır; robot yalnızca HTTP ile WAV alır.

## Proje Yapısı

- `app.py` - uvicorn import mode için giriş noktası (`app:app`)
- `remote_tts/server.py` - FastAPI route'ları
- `remote_tts/config.py` - ortam değişkenlerinden runtime config
- `remote_tts/synth.py` - Piper/XTTS sentez çağrıları
- `remote_tts/catalog.py` - ses kataloğu (piper modelleri, XTTS speaker WAV'ları)
- `remote_tts/bootstrap.py` - ilk çalıştırmada runtime/model kurulumu
- `remote_tts/static/` - basit web arayüzü

## Çalıştırma

```bash
pip install -r requirements.txt
python app.py
```

Varsayılan: `http://127.0.0.1:5000`. Docker ile `Dockerfile` hazırdır (port 5000, kalıcılık için `/app/runtime` volume).

Not: Host `0.0.0.0` gibi herkese açık bir adrese bağlanacaksa `SENTRYBOT_TTS_AUTH_TOKEN` zorunludur.

## Endpoint'ler

- `GET /healthz` - katalog/binary/bootstrap ve `WavLRUCache` durumu
- `POST /tts/synthesize` - sentez (body: `{text, engine: "piper"|"xtts", language, stream?: bool, ...}`; yanıt `audio/wav`, chunked `StreamingResponse` veya `response_format: json_base64`; `X-Cache: hit|miss` başlığı)
- `GET /tts/voices/piper` - yüklü Piper sesleri (auth korumalı)
- `GET /tts/voices/xtts` - XTTS speaker kaynakları (auth korumalı)
- `POST /tts/voices/xtts/upload` - `.wav` speaker yükleme (güvenli ASCII dosya adı/path-traversal doğrulaması, boyut sınırı `HTTP 413` ve atomik `.tmp` yazım)
- `POST /tts/refresh` - ses kataloğunu yeniden tara (auth korumalı)
- `POST /bootstrap/run` - bootstrap'ı elle çalıştır (`force` parametreli; açılışta arka plan thread'inde bloklamadan çalışır)
- `GET /ollama/tags` - Ollama model listesi proxy'si (auth korumalı, paylaşımlı `requests.Session`)
- `GET /` - web arayüzü (`/styles.css`, `/script.js`)

Kimlik doğrulama: `X-Auth-Token` header veya `Authorization: Bearer <token>` (`hmac.compare_digest` ile sabit-zamanlı doğrulama).

## Ortam Değişkenleri

- `SENTRYBOT_TTS_HOST` / `SENTRYBOT_HOST` (varsayılan `127.0.0.1`)
- `SENTRYBOT_TTS_PORT` / `SENTRYBOT_PORT` (varsayılan `5000`)
- `SENTRYBOT_TTS_AUTH_TOKEN` - public bind için zorunlu
- `SENTRYBOT_TTS_ROOT`, `SENTRYBOT_PIPER_ROOT`, `SENTRYBOT_XTTS_ROOT` - runtime dizinleri
- `SENTRYBOT_PIPER_BIN` (varsayılan `piper`), `SENTRYBOT_XTTS_BIN` (varsayılan `tts`)
- `SENTRYBOT_TTS_MAX_UPLOAD_MB` (varsayılan `25`) - `/tts/voices/xtts/upload` boyut limiti
- `SENTRYBOT_TTS_SUBPROCESS_TIMEOUT` (varsayılan `60.0`) - Piper/XTTS alt süreç zaman aşımı (`HTTP 504`)
- `SENTRYBOT_TTS_CACHE_SIZE` (varsayılan `32`, `0` kapatır) - `WavLRUCache` kapasitesi
- `SENTRYBOT_BOOTSTRAP_ON_START|FORCE|INSTALL_PIPER|INSTALL_XTTS|DOWNLOAD_PIPER_MODELS`
- `SENTRYBOT_PIPER_MODELS_SOURCE_URL`, `SENTRYBOT_BOOTSTRAP_TIMEOUT`
- `SENTRYBOT_OLLAMA_TAGS_ENDPOINT` (`Dockerfile` varsayılanı: `http://host.docker.internal:11434/api/tags`; veya `SENTRYBOT_OLLAMA_BASE_URL` / `OLLAMA_BASE_URL`), `SENTRYBOT_OLLAMA_TIMEOUT`

Not: In-process `piper.voice.PiperVoice` veya `TTS.api.TTS` Python paketleri kuruluysa modeller bellek içi önbellekte tutulur; `xtts.extra_args` yalnızca güvenli bayrak beyaz listesiyle (`_ALLOWED_XTTS_FLAGS`) kabul edilir.

## Robot Tarafı Entegrasyonu

`modules/voice/speak/services/tts_remote_backends.py` içindeki `RemoteTTSHttpBackend`, `tts.engine` `piper|xtts` iken `tts.remote.enabled: true` olursa istekleri bu sunucunun `/tts/synthesize` yoluna gönderir; `XTTSHttpBackend` ise doğrudan `tts.xtts.endpoint` kullanır.
