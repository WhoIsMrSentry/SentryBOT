# Sub-Agent: agent_core-specialist

## Uzmanlık
`xAgentCoreService` ve `agent_core` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/agent_core.md`

## Bileşen haritası
- `ActionArbiter` — Thread-safe central arbiter for all robot actions.
- `ActionPriority` — modules/agent_core/services/action_arbiter.py
- `ActionRequest` — A single action submitted to the arbiter.
- `AgentOrchestrator` — SentryBOT's Embodied AI - Native Tool Calling Edition.
- `ExpressionArbiter` — modules/agent_core/services/expression_arbiter.py
- `IdleBehaviorSystem` — Lightweight background "life signs" that run without waking up the LLM
- `EpisodicMemory` — Long-term memory vector store / SQL DB for SentryBOT.
- `MemoryConsolidator` — modules/agent_core/services/memory_consolidator.py
- `ProgressManager` — Manages staged execution progress with TTS forwarding.
- `ActionSafetyFilter` — Validates and clamps arguments for hardware tools to prevent damage.
- `SemanticIndex` — Reusable in-memory index over ``(id, text)`` documents.
- `SensorFeedbackLoop` — Background thread that periodically reads real sensor data via ServiceClient

## Dış bağlantılar (neden)
- [[autonomy]] (import): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- [[autonomy]] (registry): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- [[common]] (import): `agent_core` içinde `vision_availability` import edilir; `common` modülünün yeteneğini kullanır (Kanonik duygu sözlüğü (eyes/LEDs/ears/tone tek taksonomi)).
- [[common]] (import): `agent_core` → `common`: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- [[config_center]] (import): `agent_core` → `config_center`: config/agent.yaml dosyasından ayar okur.
- [[config_center]] (import): `agent_core` içinde `gemini_model` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).
- [[gateway]] (import): `agent_core` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- [[logwrapper]] (import): `agent_core` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- [[ollama]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[ollama]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[ollama]] (registry): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- [[social_db]] (import): Kullanıcı/tanıma verisi için sosyal hafızayı kullanır.

## Gelen bağlantılar (neden)
- [[autonomy]] (http): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[autonomy]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[autonomy]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- [[gateway]] (http): `gateway` → `agent_core`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `agent_core`: Ajan orkestrasyonu ve tool-calling çağrısı.
- [[gateway]] (import): `gateway` kod içinde `agent_core` modülünü import eder (`api`) — 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling.
- [[gateway]] (import): `gateway` kod içinde `agent_core` modülünü import eder (`services`) — 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling.
- [[speech]] (http): `speech` → `agent_core`: Ses tanıma (ASR) pipeline'ına istek gönderir.
