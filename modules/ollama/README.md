# Ollama

SentryBOT'un merkezi LLM gateway modülüdür. Sohbet, persona yönetimi ve LLM istemci fabrikasını sağlar. Adı "Ollama" olsa da sağlayıcı katmanı artık Google AI Studio/Gemini profilini de destekler.

## Sorumluluklar

- LLM istemci fabrikası (`create_llm_client`)
- Chat endpoint'leri ve structured response modu
- Persona seçimi/yönetimi
- Model listeleme ve ekleme
- Autonomy'ye action forwarding (`apply_actions`)

## Mimari

- Giriş noktası: `xOllamaService.py`
- İstemciler: `services/clients.py` (`OllamaClient`, `GoogleAIStudioClient`)
- Chat: `services/chat.py`
- Router parçaları: `api/chat_routes.py`, `api/persona_routes.py`, `api/models_routes.py`, `api/health.py`

## Sağlayıcı Politikası

`create_llm_client(cfg)` sağlayıcıyı `llm.provider` alanından seçer:
- `ollama` → `OllamaClient`
- `google`, `google_ai_studio`, `gemini` → `GoogleAIStudioClient`

Graph'ta çağrıcılar:
- `agent_core.services.agent.AgentOrchestrator`
- `vlm_bridge.services.llm_client`
- `ollama` router/service bootstrap

Strict single-model politikası modül config'inde zorlanabilir; `agent_core` tarafında ayrıca model politikası uygulanır.

## API (Gateway altında `/ollama/*`)

- `GET /ollama/healthz`
- `GET|POST /ollama/chat`
- `GET /ollama/persona`, `/personas`
- `GET /ollama/models`
- `POST /ollama/model/add`
- `POST /ollama/persona/select`
- `POST /ollama/persona/create_from_url`

Structured mode: `structured=true` → `{ text, thoughts, actions }`

## Konfigürasyon

Merkezi `config/agent.yaml` bölümleri:
- `agent`
- `llm`
- `ollama`
- `ollama_service`
- `google_ai_studio` (Google profili seçildiyse)
- `persona`
- `actions`

Persona klasörleri: `modules/ollama/config/personalities/<name>/`

## İlişkiler

- `agent_core`: ana ajan LLM çağrıları
- `autonomy`: companion chat ve LLM kararları
- `vlm_bridge`: metin üretimi fallback/chat endpoint'i
- `speech`: tanınan metin → chat → `speak` akışında ara katman

## Çalıştırma

```bash
python -m modules.ollama.xOllamaService
```

Gateway aktifken modül ayrı servis olarak başlatılmadan `/ollama/*` altında sunulur.
