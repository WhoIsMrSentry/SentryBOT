# Ollama Module

Central LLM gateway for SentryBOT. Provides FastAPI endpoints to chat with an Ollama model using configurable personas.

## Endpoints
- GET /ollama/healthz
- GET/POST /ollama/chat?query=...
	- **Structured Mode**: `structured=true` parametresi ile `SentryResponse` Pydantic şemasına zorlanmış JSON döner: `{ text: "...", thoughts: "...", actions: [...] }`.
	- **Normal Mode**: Geriye dönük uyumluluk için `answer` (text) ve `raw` alanlarını içeren bir yapı döner.
	- `apply_actions=true` sorgu parametresi gönderilirse, `actions` alanı Autonomy servisinin `/autonomy/apply_actions` ucuna iletilir.

## Supported Actions (Hardware & System)
Ollama artık robotu aşağıdaki aksiyon türleri ile kontrol edebilir:
- `servo`: Kafa hareketi (pan/tilt).
- `lights`: NeoPixel animasyonları (mode, emotions, intensity).
- `laser`: Lazer kontrolü (id, on, both).
- `buzzer` / `sound_play`: Sesli uyarılar.
- `system`: Modül kontrolü (`notifier`, `camera`, `autonomy`).
- `speak`: Özel tonlama gerektiren sesli yanıtlar.
- `anim`: Hazır animasyon sekansları.
- `stand` / `sit` / `home`: Pozisyon komutları.
- GET /ollama/persona
- GET /ollama/personas
- GET /ollama/models
- POST /ollama/model/add (name, set_default)
- POST /ollama/persona/select (name)
- POST /ollama/persona/create_from_url (name, url)

## Config
See `modules/ollama/config/config.yml`.

`.env` overrides are supported via `modules/ollama/.env`.
Useful keys:
- `LLM_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://<external-ip>:11435`
- `OLLAMA_MODEL=llama3.2:3b`

Personas now live as folders: `modules/ollama/config/personalities/<name>/{persona.txt,urls.txt}`.

## Run
This module is meant to be imported by other modules (e.g., interactions, speech). It can also run as a service via `python -m modules.ollama.xOllamaService`.

## Integration contract (other modules)
- Speech: send recognized text → call `POST /ollama/chat` → receive `answer` (string)
	- Then pass `answer` to Speak module `/speak/say` for TTS.
	- Interactions/Neopixel: `actions.blocks` alanını kullanarak LED / servo değişikliklerini otomatik tetikleyebilir veya `apply_actions=true` ile Autonomy'ye devredebilirsiniz.
- Camera: can request `answer` for descriptions or next actions; not directly dependent.

All persona handling is centralized here; modules should not embed prompts. Use persona select to switch tone/role globally.

## Gateway ile Kullanım
Gateway çalışırken bu uçlar tek portta `/ollama/*` altında sunulur; modülü ayrı servis olarak çalıştırmaya gerek yoktur.
