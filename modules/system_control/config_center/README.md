# Platform - Config Center

SentryBOT'un merkezi yapılandırma yönetim modülüdür. Modül YAML dosyalarını görüntüler/düzenler, runtime anahtarlarını yönetir ve `config/agent.yaml` için **tek kaynak** yükleme katmanını sağlar.

## Sorumluluklar

- **Merkezi `config/agent.yaml` yükleme** (`agent_yaml_loader.load_agent_config`) — **TEK KAYNAK**
- Modül `config.yml` dosyalarını listeleme, okuma, yazma (CRUD)
- Web tabanlı config UI (`/config/ui`)
- Runtime config registry (canlı anahtar/değer yönetimi + `apply_fn`)
- YAML runtime apply (modül davranışını anında güncelleme)
- Google API key enjeksiyonu, runtime auth token env overlay ve loopback URL rewrite

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xConfigCenterService.py`
- **Agent YAML Loader**: `agent_yaml_loader.py` (~84 satır) — büyük duplication giderildi, ayrıca aşağıdaki nota bakın
- **Runtime Registry**: `services/runtime_registry.py` → `RuntimeConfigRegistry` (register, set, apply_fn)
- **Runtime Apply**: `services/yaml_runtime_apply.py` → `apply_runtime_config()`
- **API Parçaları**: `api/config_routes.py`, `api/write.py`, `api/runtime.py`, `api/scan.py`, `api/views.py`
- **Secrets**: `runtime_secrets.py` — env token inject, redaction
- **Google Keys**: `google_keys.py` — Google AI Studio key validation
- **Runtime Profile**: `runtime_profile.py` — profile merge/resolve

`load_agent_config()` graph'ta **40+ çağrıcıya** sahiptir; `agent_core`, `voice/speech`, `voice/speak`, `ai_provider`, `gateway`, `vlm_bridge`, `voice/wakeword` gibi modüller merkezi config'i buradan okur.

## API (Gateway altında `/config/*`)

### Config Dosya Yönetimi
- `GET /config/list` — modül config dosyaları
- `GET /config/get?module=<name>` — parsed config
- `GET /config/raw?module=<name>` — raw YAML
- `PUT /config/set?module=<name>` — config güncelle (backup + validate)
- `POST /config/register` — yeni modül config kaydet
- `POST /config/scan` — modül keşfi
- `GET /config/ui` — Web UI

### Runtime Registry
- `GET /config/runtime/list` — tüm runtime key'ler
- `GET /config/runtime/get?key=<module.name>`
- `POST /config/runtime/set` — `{key, value}` → `apply_fn` tetikler
- `GET /config/runtime/audit` — değişiklik geçmişi

## Özellikler

- YAML doğrulama ve kaydetmeden önce backup (timestamp)
- Otomatik kaydet (debounce 500ms)
- Modül keşfi (`scan`) — `modules/*/config/config.yml` tarar
- Gateway bootstrap sırasında `RuntimeConfigRegistry` oluşturulur ve runtime key'ler kaydedilir (`bootstrap_config.py:_register_runtime_keys`)

## Konfigürasyon

`modules/system_control/config_center/config/config.yml` içinde panel/modül listesi tutulur. Merkezi agent config dosyası varsayılan olarak `config/agent.yaml`'dır; `AGENT_CFG` env ile override edilebilir.

**Canlı token'lar YAML'de tutulmaz.** Repo kökü `.env` (gitignore) veya ortam değişkenleri:
- `SENTRYBOT_AGENT_AUTH_TOKEN`
- `SENTRYBOT_VLM_AUTH_TOKEN`
- `SENTRYBOT_TTS_AUTH_TOKEN`
- `GOOGLE_API_KEY`

Örnek: `config/agent.secrets.env.example`. Git geçmişindeki eski token'lar döndürülmeli.

## İlişkiler (Güncel Modül Yolları)

**Consumer (config okur):**
- `agent_core`, `voice/speech`, `voice/speak`, `ai_provider`, `gateway`, `vlm_bridge`, `voice/wakeword`, `autonomy`, `camera`, `arduino_serial`, `expression`, `visual_output`, `cognitive_memory` — hepsi `load_agent_config()` çağırır

**Provider (runtime key yazır):**
- `gateway/bootstrap_config.py:_register_runtime_keys()` — VLM modes, agent profiles, IMX500, state_manager operational

## ✅ ÇÖZÜLDÜ: CONFIG LOADER DUPLICATION BÜYÜK ÖLÇÜDE GİDERİLDİ

Eskiden `ai_provider/config_loader.py` (6407 satır) ile `agent_yaml_loader.py` (2815 satır) neredeyse aynı kodu içeriyordu. Şu an durum:

- `ai_provider/config_loader.py` artık `common/config_loader.py`'dan import ediyor — duplicate kalmadı.
- `agent_yaml_loader.py` **~84 satıra** indi; merger/validator/scanner/secrets/runtime_profile/google_keys parçaları kaldırıldı.

**NOT:** `agent_yaml_loader.py` hâlâ `common.config_loader`'a bağlanmayan **bağımsız mini `load_agent_config`** içeriyor — tam birleşme (tek kaynak `modules/common/config_loader.py`) bekliyor.

## Bilinen Sorunlar

1. **Tam Birleşme Bekliyor** - `agent_yaml_loader.py` içindeki bağımsız mini `load_agent_config`, `common.config_loader`'a henüz bağlanmadı (yukarıdaki NOT).
2. **Runtime Registry Apply Fn Sync** - `apply_fn` sync çağrılıyor, modül `stop()/start()` blokluyorsa deadlock riski. Async apply + timeout gerekli.
3. **UI Static Dosyaları** - `static/css/styles.css`, `static/js/app.js`, `static/index.html` — güncel mi? React/Vue yok, vanilla JS.
4. **Secrets Redaction** - `runtime_secrets.py` redaction var ama `agent.yaml` yazılırken token'lar temizlenmeli (backup'ta da).