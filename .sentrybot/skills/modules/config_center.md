# Skill: config_center

## Ana bileşen
- Sınıf: `None` in `modules/config_center/xConfigCenterService.py`
- Mission: Merkezi config okuma/yazma, hot-reload

## API özeti
- `GET /ui` → `ui()` → —
- `GET /static/{file_path:path}` → `serve_static()` → —
- `GET /list` → `list_modules()` → —
- `GET /get` → `get_config()` → —
- `GET /raw` → `get_config_raw()` → —
- `PUT /set` → `set_config()` → —
- `POST /register` → `register()` → —
- `GET /runtime/list` → `runtime_list()` → —
- `GET /runtime/get` → `runtime_get()` → —
- `POST /runtime/set` → `runtime_set()` → —

## Dış ilişkiler (neden)
- → [[gateway]] (import): Runtime config ve modül registry gateway ile senkronize edilir.
- → [[ollama]] (import): `config_center` içinde `services` import edilir; `ollama` modülünün yeteneğini kullanır (Ollama LLM chat, persona yönetimi, JSON/XML parse).
- → [[social_db]] (import): `config_center` içinde `get_default` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).
- → [[social_db]] (import): `config_center` içinde `db` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).

## Gelen ilişkiler (neden)
- ← [[agent_core]] (import): `agent_core` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- ← [[agent_core]] (import): `agent_core` kod içinde `config_center` modülünü import eder (`gemini_model`) — Merkezi config okuma/yazma, hot-reload.
- ← [[arduino_serial]] (import): `arduino_serial` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- ← [[autonomy]] (import): `autonomy` kod içinde `config_center` modülünü import eder (`log_redact`) — Merkezi config okuma/yazma, hot-reload.
- ← [[esp_link]] (import): `esp_link` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- ← [[gateway]] (http): `gateway` → `config_center`: Merkezi yapılandırma okur/yazar.
- ← [[gateway]] (import): `gateway` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- ← [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`config_loader`) — Merkezi config okuma/yazma, hot-reload.
- ← [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`api`) — Merkezi config okuma/yazma, hot-reload.
- ← [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`services`) — Merkezi config okuma/yazma, hot-reload.

## Tam bilgi
`.sentrybot/obsidian/modules/config_center.md` (23 dosya, 1457 satır)
