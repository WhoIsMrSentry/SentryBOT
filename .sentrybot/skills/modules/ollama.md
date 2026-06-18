# Skill: ollama

## Ana bileşen
- Sınıf: `RobotAction` in `modules/ollama/xOllamaService.py`
- Mission: Ollama LLM chat, persona yönetimi, JSON/XML parse

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /chat` → `chat_get()` → —
- `POST /chat` → `chat_post()` → —
- `POST /translate` → `translate()` → —
- `POST /runtime/num_predict` → `runtime_num_predict()` → —
- `GET /persona` → `get_persona()` → —
- `GET /personas` → `list_personas()` → —
- `GET /models` → `list_models()` → —
- `POST /warmup` → `warmup()` → —
- `POST /model/add` → `add_model()` → —

## Dış ilişkiler (neden)
- → [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- → [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- → [[config_center]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- → [[logwrapper]] (import): `ollama` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[agent_core]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- ← [[agent_core]] (import): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- ← [[agent_core]] (registry): Router ve Persona katmanı LLM çıkarımı için Ollama kullanır.
- ← [[autonomy]] (registry): Duygu motoru ve karar üretimi için yerel LLM'e sorar.
- ← [[config_center]] (import): `config_center` kod içinde `ollama` modülünü import eder (`services`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.
- ← [[diagnostics]] (registry): Ollama servis erişilebilirlik testi yapar.
- ← [[gateway]] (http): `gateway` → `ollama`: Yerel LLM sohbet/completion isteği yapar.
- ← [[gateway]] (http): `gateway` → `ollama`: Yerel LLM sohbet/completion isteği yapar.
- ← [[gateway]] (import): `gateway` kod içinde `ollama` modülünü import eder (`config_loader`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.
- ← [[gateway]] (import): `gateway` kod içinde `ollama` modülünü import eder (`api`) — Ollama LLM chat, persona yönetimi, JSON/XML parse.

## Tam bilgi
`.sentrybot/obsidian/modules/ollama.md` (23 dosya, 1741 satır)
