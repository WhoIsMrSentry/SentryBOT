# Ollama Module

Central LLM gateway for SentryBOT. Provides FastAPI endpoints to chat with an Ollama model using configurable personas.

## Endpoints
- GET /ollama/healthz
- GET/POST /ollama/chat?query=...
- GET /ollama/persona
- GET /ollama/personas
- POST /ollama/persona/select (name)
- POST /ollama/persona/create_from_url (name, url)

## Config
See `modules/ollama/config/config.yml`.

Personas now live as folders: `modules/ollama/config/personalities/<name>/{persona.txt,urls.txt}`.

## Run
This module is meant to be imported by other modules (e.g., interactions, speech). It can also run as a service via `python -m modules.ollama.xOllamaService`.

## Integration contract (other modules)
- Speech: send recognized text → call `POST /ollama/chat` → receive `answer` (string)
	- Then pass `answer` to Speak module `/speak/say` for TTS.
- Interactions/Neopixel: optionally parse `answer` for emotion keywords or explicit control tokens, then trigger effects.
- Camera: can request `answer` for descriptions or next actions; not directly dependent.

All persona handling is centralized here; modules should not embed prompts. Use persona select to switch tone/role globally.

## Gateway ile Kullanım
Gateway çalışırken bu uçlar tek portta `/ollama/*` altında sunulur; modülü ayrı servis olarak çalıştırmaya gerek yoktur.
