# Platform - Config Center

SentryBOT'un merkezi yapılandırma yönetim modülüdür. Modül `config.yml` dosyalarını görüntüler/doğrular/atomik günceller, geri alma (`/config/rollback`) sunar ve çalışma zamanı anahtarlarını yönetir (`modules.common.config_loader` ile entegre).

## Sorumluluklar

- **Merkezi `config/agent.yaml` yükleme:** Tek kaynak `modules.common.config_loader` üzerinden sağlanır (`config_center` altındaki 6 eski shim dosyası kaldırılmıştır).
- Modül `config.yml` dosyalarını listeleme, okuma, doğrulama (`dry_run`), atomik yazma (`os.replace`) ve geri alma (`POST /config/rollback`)
- Modül keşfi (`POST /config/scan` — çok katmanlı `rglob("config/config.yml")`)
- Opsiyonel Web UI (`/config/ui` — yalnız `static/index.html` mevcutken bağlanır)
- Runtime config registry (`services/runtime_registry.py` — non-blocking `apply_fn` + sıkı `_coerce_bool`)
- YAML runtime apply (`services/yaml_runtime_apply.py` — `clear_agent_config_cache()` + çoklu modül anahtar eşleme)

## Mimari

- Giriş noktası: `xConfigCenterService.py` (varsayılan port: `8109` — `ollama_service:8099` çakışması giderildi)
- **Config Yükleyici**: `config_loader.py` → `modules.common.config_loader.load_module_config`
- **Runtime Registry**: `services/runtime_registry.py` → `RuntimeConfigRegistry` (`_apply_lock` + `_lock` ayrımı)
- **Runtime Apply**: `services/yaml_runtime_apply.py` → `apply_module_yaml()`
- **API Parçaları**: `api/_helpers.py` (`resolve_module_config_path`, `atomic_write_text`, 5 yedeğe kadar `backup_file`, `list_backups`), `api/config_routes.py`, `api/write.py`, `api/runtime.py`, `api/scan.py`, `api/views.py`

## API (Gateway altında `/config/*`)

### Config Dosya Yönetimi
- `GET /config/list` — modül config dosyaları
- `GET /config/get?module=<name>` — parsed config
- `GET /config/raw?module=<name>` — raw YAML
- `PUT /config/set?module=<name>&dry_run=false` — YAML doğrula, `dry_run=true` ise yazmadan sonuç dön; aksi halde son 5 yedeği koruyarak atomik yaz + runtime apply
- `POST /config/rollback?module=<name>&backup_name=` — son (veya seçili) `.bak-*` yedeğini atomik geri yükle + runtime apply
- `POST /config/register` — yeni modül config kaydet
- `POST /config/scan` — `modules/**/config/config.yml` özyinelemeli keşfi
- `GET /config/ui` — Web UI (yalnız `static/index.html` varsa aktif)

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

## ✅ ÇÖZÜLDÜ: CONFIG LOADER DUPLICATION TAMAMEN GİDERİLDİ

Eskiden `ai_provider/config_loader.py` (6407 satır) ile `agent_yaml_loader.py` (2815 satır) neredeyse aynı kodu içeriyordu. Şu an durum:

- `ai_provider/config_loader.py` artık `common/config_loader.py`'dan import ediyor — duplicate kalmadı.
- `modules/common/config_loader.py` **TEK KAYNAK** (`load_agent_config`) olarak belirlendi.
- `agent_yaml_loader.py` geriye dönük uyumluluk için `modules.common.config_loader`'a yönlendiren ince bir shim olarak güncellendi.

## Bilinen Sorunlar

1. **Runtime Registry Apply Fn Sync** - `apply_fn` sync çağrılıyor, modül `stop()/start()` blokluyorsa deadlock riski. Async apply + timeout gerekli.
2. **UI Static Dosyaları** - `static/css/styles.css`, `static/js/app.js`, `static/index.html` — güncel mi? React/Vue yok, vanilla JS.
3. **Secrets Redaction** - `runtime_secrets.py` redaction var ama `agent.yaml` yazılırken token'lar temizlenmeli (backup'ta da).