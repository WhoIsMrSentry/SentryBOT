# Config Center

SentryBOT'un merkezi yapılandırma yönetim modülüdür. Modül YAML dosyalarını görüntüler/düzenler, runtime anahtarlarını yönetir ve `config/agent.yaml` için tek kaynak yükleme katmanını sağlar.

## Sorumluluklar

- Merkezi `config/agent.yaml` yükleme (`agent_yaml_loader.load_agent_config`)
- Modül `config.yml` dosyalarını listeleme, okuma, yazma
- Web tabanlı config UI (`/config/ui`)
- Runtime config registry (canlı anahtar/değer yönetimi)
- YAML runtime apply (modül davranışını anında güncelleme)
- Google API key enjeksiyonu ve loopback URL rewrite

## Mimari

- Giriş noktası: `xConfigCenterService.py`
- Agent YAML: `agent_yaml_loader.py`
- Runtime registry: `services/runtime_registry.py`
- Runtime apply: `services/yaml_runtime_apply.py`
- API parçaları: `api/config_routes.py`, `api/write.py`, `api/runtime.py`, `api/scan.py`, `api/views.py`

`load_agent_config()` graph'ta 40+ çağrıcıya sahiptir; `agent_core`, `speech`, `speak`, `ollama`, `gateway`, `vlm_bridge`, `wakeword` gibi modüller merkezi config'i buradan okur.

## API

### Config dosya yönetimi

- `GET /config/healthz`
- `GET /config/list`
- `GET /config/get?module=<name>`
- `GET /config/raw?module=<name>`
- `PUT /config/set?module=<name>`
- `POST /config/register`
- `POST /config/scan`
- `GET /config/ui`

### Runtime registry

- `GET /config/runtime/list`
- `GET /config/runtime/get?key=<module.name>`
- `POST /config/runtime/set`
- `GET /config/runtime/audit`

## Özellikler

- YAML doğrulama ve kaydetmeden önce backup
- Otomatik kaydet (debounce)
- Modül keşfi (`scan`)
- Gateway bootstrap sırasında `RuntimeConfigRegistry` oluşturulur ve runtime key'ler kaydedilir

## Konfigürasyon

Modül-içi `config/config.yml` içinde panel/modül listesi tutulur. Merkezi agent config dosyası varsayılan olarak `config/agent.yaml`'dır; `AGENT_CFG` ile override edilebilir.

## İlişkiler

Bu modül, dağıtık modül config'leri ile merkezi agent config'i arasındaki köprüdür. Otonom davranış veya LLM politikası değişikliklerinin çoğu buradan okunan YAML üzerinden yürür.
