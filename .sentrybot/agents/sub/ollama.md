# Sub-Agent: ollama-specialist

## Uzmanlık
`RobotAction` ve `ollama` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/ollama.md`

## Bileşen haritası
- `RobotAction` — modules/ollama/models/sentry_schema.py
- `OllamaChatService` — modules/ollama/services/chat.py
- `GoogleAIStudioClient` — Google AI Studio (Gemini) REST istemcisi.
- `LLMClientProtocol` — modules/ollama/services/clients.py
- `OllamaClient` — modules/ollama/services/clients.py
- `ChatMemory` — modules/ollama/services/memory.py
- `OllamaTranslator` — Small translation facade that uses Ollama chat with strict prompts.
- `TranslatorConfig` — modules/ollama/services/translator.py

## Dış bağlantılar (neden)
- [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- [[logwrapper]] (import): `ollama` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[agent_core]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[agent_core]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[agent_core]] (registry): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[autonomy]] (registry): Duygu motoru ve karar üretimi için yerel LLM'e sorar.
- [[config_center]] (import): `config_center` kod içinde `ollama` modülünü import eder (`services`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.
- [[diagnostics]] (registry): Ollama servis erişilebilirlik testi yapar.
- [[gateway]] (http): `gateway` → `ollama`: Yerel LLM sohbet/completion isteği yapar.
- [[gateway]] (http): `gateway` → `ollama`: Yerel LLM sohbet/completion isteği yapar.
- [[gateway]] (import): `gateway` kod içinde `ollama` modülünü import eder (`config_loader`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.
- [[gateway]] (import): `gateway` kod içinde `ollama` modülünü import eder (`api`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.
- [[vlm_bridge]] (http): Remote VLM veya scene caption için LLM'e danışır.
- [[vlm_bridge]] (import): Remote VLM veya scene caption için LLM'e danışır.
