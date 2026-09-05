# Cognition - AI Provider (LLM Gateway)

SentryBOT'un merkezi LLM gateway modülüdür. Sohbet, persona yönetimi ve LLM istemci fabrikasını sağlar. Adı "Ollama" olsa da sağlayıcı katmanı artık **Google AI Studio/Gemini** profilini de destekler.

## Sorumluluklar

- LLM istemci fabrikası (`create_llm_client`) — **Tek kaynak**
- Chat endpoint'leri ve structured response modu (`{ text, thoughts, actions }`)
- Persona seçimi/yönetimi
- Model listeleme ve ekleme
- Autonomy/agent_core'ye action forwarding (`apply_actions`)

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xOllamaService.py` → `OllamaService` (legacy isim, sınıf adı kalabilir)
- **İstemciler**: `services/clients.py` → `OllamaClient`, `GoogleAIStudioClient`, `BaseLLMClient` (abstract)
- **Chat**: `services/chat.py` → `ChatService` (structured response logic)
- **Router Parçaları**: `api/chat_routes.py`, `api/persona_routes.py`, `api/models_routes.py`, `api/health.py`
- **Config**: `config_loader.py` — **KRİTİK: `config_center/agent_yaml_loader.py` ile DUPLICATE**

## Sağlayıcı Politika

`create_llm_client(cfg)` sağlayıcıyı `llm.provider` alanından seçer:
- `ollama` → `OllamaClient` (local Ollama server)
- `google`, `google_ai_studio`, `gemini` → `GoogleAIStudioClient` (Google AI Studio / Gemini API)

Graph'ta çağrıcılar:
- `cognition/agent_core/services/agent.AgentOrchestrator` — ana ajan LLM çağrıları
- `perception/vision/vlm_bridge/services/llm_client` — semantic scene generation
- `cognition/autonomy` — companion chat ve LLM kararları
- `voice/speech` — tanınan metin → chat → `speak` akışında ara katman

**Strict single-model politika** modül config'inde zorlanabilir; `agent_core` tarafında ayrıca model politikası uygulanır.

## API (Gateway altında `/ollama/*`)

Router prefix **yalnızca `/ollama`** (`api/router.py:88`). Gateway'de `/ai_provider` alias/mount **yoktur** — `/ai_provider/*` uçları çağrılabilir DEĞİLDİR; "ai_provider" yalnızca merkezi config'deki bölüm adıdır. Gateway bootstrap, modülü `include.ollama: true` ile kendi router'ı üzerinden mount eder.

- `GET /ollama/healthz`
- `GET|POST /ollama/chat`
- `POST /ollama/warmup`
- `POST /ollama/translate`
- `POST /ollama/runtime/num_predict`
- `GET /ollama/persona`, `/personas`
- `GET /ollama/models`
- `POST /ollama/model/add`
- `POST /ollama/persona/select`
- `POST /ollama/persona/create_from_url`

**Structured mode:** `structured=true` → `{ text, thoughts, actions }` (agent tool calling için)

## Konfigürasyon

Merkezi `config/agent.yaml` bölümleri (tek kaynak `common/config_loader.py:612`):

- `agent` — agent_core config
- `llm` — provider, model, timeout, request params
- `ai_provider` (eski `ollama`) — base_url, model, timeout
- `google_ai_studio` — api_key, model, safety_settings (Google profili seçildiyse)
- `persona` — aktif persona, personas listesi
- `actions` — action forwarding endpoint (`/autonomy/apply_actions`)

Persona klasörleri: `modules/ai_provider/config/personalities/<name>/` (modelfile, persona.txt)

## İlişkiler (Güncel Modül Yolları)

- `cognition/agent_core` — ana ajan LLM çağrıları (tool calling, tri-layer)
- `cognition/autonomy` — companion chat, LLM kararları, proactive scene comment
- `perception/vision/vlm_bridge` — metin üretimi fallback, semantic scene (`llm_client.py`)
- `voice/speech` — tanınan metin → chat → `voice/speak` akışında ara katman
- `common/config_loader` — **TEK KAYNAK** (eski `platform/config_center` ile birleşti)

## ✅ DÜZELTİLDİ (2026-08-21): CONFIG LOADER BİRLEŞTİRİLDİ

`common/config_loader.py:612 load_agent_config` tek kaynak yapıldı. `ai_provider/config_loader.py:179` artık `common` import ediyor, duplicate kalmadı. Graph kanıtı: `nodes 11736` içinde `common core 55 in`.

## Bilinen Sorunlar

1. **Config Loader Duplication (Yukarıda)** - En büyük teknik borç. 40+ modül etkilenen.
2. **xOllamaService Sınıf Adı** - Modül `ai_provider` ama sınıf `OllamaService`. `AIProviderService` veya `LLMGatewayService` olmalı.
3. **GoogleAIStudioClient Error Handling** - API key invalid, quota exceeded, rate limit durumlarında retry/backoff zayıf.
3. **Structured Response Parser** - `services/chat.py` içinde basit regex/json parse. `agent_core` tool calling formatı ile tutarlı olmalı (OpenAI function calling format).
4. **Model Policy Çakışması** - `agent_core` kendi `_get_active_persona_model()` + `realtime_profile` var, `ai_provider` kendi `create_llm_client()` var. **Tek model policy: `modules/common/model_policy.py`**
5. **Persona Reload** - `POST /persona/select` sonrası `agent_core` ve `autonomy` yeni persona'yı nasıl alır? Event bus yok, polling yapıyorlar.