# Sub-Agent: config_center-specialist

## Uzmanlık
`None` ve `config_center` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/config_center.md`

## Bileşen haritası
- `RuntimeConfigRegistry` — Thread-safe registry mapping ``module.key`` -> :class:`RuntimeKey`.
- `RuntimeKey` — Descriptor for a single hot-applyable configuration key.

## Dış bağlantılar (neden)
- [[gateway]] (import): Runtime config ve modül registry gateway ile senkronize edilir.
- [[ollama]] (import): `config_center` içinde `services` import edilir; `ollama` modülünün yeteneğini kullanır (Ollama LLM chat, persona yönetimi, JSON/XML parse).
- [[social_db]] (import): `config_center` içinde `get_default` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).
- [[social_db]] (import): `config_center` içinde `db` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).

## Gelen bağlantılar (neden)
- [[agent_core]] (import): `agent_core` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- [[agent_core]] (import): `agent_core` kod içinde `config_center` modülünü import eder (`gemini_model`) — Merkezi config okuma/yazma, hot-reload.
- [[arduino_serial]] (import): `arduino_serial` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- [[autonomy]] (import): `autonomy` kod içinde `config_center` modülünü import eder (`log_redact`) — Merkezi config okuma/yazma, hot-reload.
- [[esp_link]] (import): `esp_link` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- [[gateway]] (http): `gateway` → `config_center`: Merkezi yapılandırma okur/yazar.
- [[gateway]] (import): `gateway` `config_center` modülünden `agent_yaml_loader` kullanır: config/agent.yaml dosyasından ayar okur.
- [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`config_loader`) — Merkezi config okuma/yazma, hot-reload.
- [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`api`) — Merkezi config okuma/yazma, hot-reload.
- [[gateway]] (import): `gateway` kod içinde `config_center` modülünü import eder (`services`) — Merkezi config okuma/yazma, hot-reload.
- [[ollama]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
- [[ollama]] (import): LLM model ve persona ayarlarını merkezi config'den okur.
