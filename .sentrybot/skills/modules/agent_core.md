# Skill: agent_core

## Ana bileşen
- Sınıf: `xAgentCoreService` in `modules/agent_core/xAgentCoreService.py`
- Mission: 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling

## API özeti
- `GET /healthz` → `healthz()` → —
- `POST /speech/interrupt` → `speech_interrupt()` → —
- `POST /step` → `step()` → —
- `POST /step_stream` → `step_stream()` → —
- `POST /route_preview` → `route_preview()` → —
- `GET /world_state` → `world_state()` → —
- `GET /memory/search` → `search_memory()` → —
- `GET /slam/location` → `get_location()` → —
- `GET /slam/pathfind` → `pathfind()` → —
- `GET /actions/status` → `actions_status()` → —

## Dış ilişkiler (neden)
- → [[autonomy]] (import): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- → [[autonomy]] (registry): Alt sistem olarak otonomi beyin döngüsünü tetikler.
- → [[common]] (import): `agent_core` içinde `vision_availability` import edilir; `common` modülünün yeteneğini kullanır (Kanonik duygu sözlüğü (eyes/LEDs/ears/tone tek taksonomi)).
- → [[common]] (import): `agent_core` → `common`: Kanonik duygu taksonomisi (tone/LED/yüz) için ortak sözlük.
- → [[config_center]] (import): `agent_core` → `config_center`: config/agent.yaml dosyasından ayar okur.
- → [[config_center]] (import): `agent_core` içinde `gemini_model` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).
- → [[gateway]] (import): `agent_core` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- → [[logwrapper]] (import): `agent_core` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- → [[ollama]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- → [[ollama]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.

## Gelen ilişkiler (neden)
- ← [[autonomy]] (http): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- ← [[autonomy]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- ← [[autonomy]] (import): Üst seviye ajan orkestrasyonu ve tool-calling entegrasyonu.
- ← [[gateway]] (http): `gateway` → `agent_core`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[gateway]] (http): `gateway` → `agent_core`: Ajan orkestrasyonu ve tool-calling çağrısı.
- ← [[gateway]] (import): `gateway` kod içinde `agent_core` modülünü import eder (`api`) — 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling.
- ← [[gateway]] (import): `gateway` kod içinde `agent_core` modülünü import eder (`services`) — 3-katmanlı ajan zekâ (Router→Sub-Agent→Persona), tool calling.
- ← [[speech]] (http): `speech` → `agent_core`: Ses tanıma (ASR) pipeline'ına istek gönderir.

## Tam bilgi
`.sentrybot/obsidian/modules/agent_core.md` (44 dosya, 6493 satır)
