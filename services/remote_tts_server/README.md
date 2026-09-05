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

- `GET /healthz` - katalog/binary/bootstrap durumu
- `POST /tts/synthesize` - sentez (body: `{text, engine: "piper"|"xtts", language, ...}`; yanıt WAV veya `response_format: json_base64`)
- `GET /tts/voices/piper` - yüklü Piper sesleri
- `GET /tts/voices/xtts` - XTTS speaker kaynakları
- `POST /tts/voices/xtts/upload` - `.wav` speaker yükleme
- `POST /tts/refresh` - ses kataloğunu yeniden tara
- `POST /bootstrap/run` - bootstrap'ı elle çalıştır (`force` parametreli)
- `GET /ollama/tags` - Ollama model listesi proxy'si
- `GET /` - web arayüzü (`/styles.css`, `/script.js`)

Kimlik doğrulama: `X-Auth-Token` header veya `Authorization: Bearer <token>`.

## Ortam Değişkenleri

- `SENTRYBOT_TTS_HOST` / `SENTRYBOT_HOST` (varsayılan `127.0.0.1`)
- `SENTRYBOT_TTS_PORT` / `SENTRYBOT_PORT` (varsayılan `5000`)
- `SENTRYBOT_TTS_AUTH_TOKEN` - public bind için zorunlu
- `SENTRYBOT_TTS_ROOT`, `SENTRYBOT_PIPER_ROOT`, `SENTRYBOT_XTTS_ROOT` - runtime dizinleri
- `SENTRYBOT_PIPER_BIN` (varsayılan `piper`), `SENTRYBOT_XTTS_BIN` (varsayılan `tts`)
- `SENTRYBOT_BOOTSTRAP_ON_START|FORCE|INSTALL_PIPER|INSTALL_XTTS|DOWNLOAD_PIPER_MODELS`
- `SENTRYBOT_PIPER_MODELS_SOURCE_URL`, `SENTRYBOT_BOOTSTRAP_TIMEOUT`
- `SENTRYBOT_OLLAMA_TAGS_ENDPOINT` (veya `SENTRYBOT_OLLAMA_BASE_URL` / `OLLAMA_BASE_URL`), `SENTRYBOT_OLLAMA_TIMEOUT`

## Robot Tarafı Entegrasyonu

`modules/voice/speak/services/tts_remote_backends.py` içindeki `RemoteTTSHttpBackend`, `tts.engine` `piper|xtts` iken `tts.remote.enabled: true` olursa istekleri bu sunucunun `/tts/synthesize` yoluna gönderir; `XTTSHttpBackend` ise doğrudan `tts.xtts.endpoint` kullanır.
