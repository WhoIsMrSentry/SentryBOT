# Common — SentryBOT Çekirdek Ortak Kütüphanesi

`modules.common`, SentryBOT platformundaki tüm servislerin paylaştığı konfigürasyon, model yönetim politikası, thread-safe olay dağıtımı (event bus) ve HTTP istemcisi gibi ortak araçları barındıran çekirdek modüldür.

Mimari detaylar, sınıf yapıları ve veri akış diyagramları için:
- 📖 [architecture_common.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/common/architecture_common.md)
- 📊 [architecture_common.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/common/architecture_common.dot) (Graphviz DOT kaynağı)

---

## 🚀 Temel Özellikler

1. **Konfigürasyon Yükleyici (`config_loader`):** `agent.yaml`, runtime profilleri ve modül konfigürasyonlarını birleştirir (`load_agent_config`, `load_ai_provider_config`); `ai_provider` / `ollama_service` bölümlerini ve `llm.single_model_mode` / `llm.required_model` ayarlarını destekler.
2. **Model Politikası (`model_policy`):** Yerel Ollama (`qwen3.5:9b`) ve esnek tek-model/çoklu-model modlarını thread-safe (`threading.Lock`) yönetir; Ollama URL temizliğini `ollama_url` modülüne devreder.
3. **Ollama URL Koruyucusu (`ollama_url`):** `DEFAULT_LOCAL_OLLAMA_URL` / `DEFAULT_REMOTE_OLLAMA_URL` sabitleriyle döngüsel Gateway yönlendirmelerini engeller, bozuk adresleri normalize eder.
4. **Güvenli HTTP İstemcisi (`http_client`):** `AsyncHTTPClient` / `SyncHTTPClient`, per-segment gateway circuit-breaker izolasyonu, monotonic zamanlama ve 4xx koruma desteği sağlar.
5. **Log Sağlayıcı ve Telemetri (`logger`, `runtime_target`):** `register_log_provider(...)` ile UI bağımlılığını ayırır; `read_hardware_pressure()` ile subprocess açmadan CPU sıcaklığı ve RAM baskısını raporlar.
6. **Görüş & Varlık Doğrulama (`vision_availability`, `model_asset_truth`):** Paylaşımlı `requests.Session` + `1.0s` TTL önbellekleme (`clear_vision_cache`) ve `config/model_assets.json` ile senkronize varlık kontrolü sunar.
7. **Servis, Kalıcılık, İş & Komut Kayıt Defterleri (`service_base`, `persistence`, `job_types`, `command_registry`, `router_factory`, `health`):** Ortak yaşam döngüsü, SQLite `GLOB` / atomik JSON kalıcılığı, oturum/kayıt yardımcıları, FastAPI router fabrikası ve kayan pencere rate limiter içerir.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. Konfigürasyon Yükleme
```python
from modules.common.config_loader import load_agent_config

cfg = load_agent_config()
port = cfg.get("server", {}).get("port", 8080)
```

### 2. Model ve Sağlayıcı Çözümleme
```python
from modules.common.model_policy import get_model_policy

policy = get_model_policy()
provider_cfg = policy.get_provider_config(cfg)
print(provider_cfg["provider"])  # "ollama" veya "google_ai_studio"
print(provider_cfg["model"])     # "qwen3.5:9b" veya "gemini-2.5-flash"
```

### 3. Olay Yayınlama ve Dinleme
```python
from modules.common.event_bus import get_event_bus

bus = get_event_bus()

# Dinleyici ekleme
bus.subscribe("VISION", lambda event: print(f"Yeni görüntü olayı: {event.data}"))

# Olay yayınlama
bus.publish("VISION", {"detected": "person", "confidence": 0.94})
```

### 4. URL Sanitizasyonu
```python
from modules.common.ollama_url import normalize_ollama_url

# Bozuk veya gateway portu verilen adresi güvenli varsayılana çeker:
safe_url = normalize_ollama_url("http://127.0.0.1:8080/ollama")
assert safe_url == "http://127.0.0.1:11434"
```

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/common -v
```