# Common — SentryBOT Çekirdek Ortak Kütüphanesi

`modules.common`, SentryBOT platformundaki tüm servislerin paylaştığı konfigürasyon, model yönetim politikası, thread-safe olay dağıtımı (event bus) ve HTTP istemcisi gibi ortak araçları barındıran çekirdek modüldür.

Mimari detaylar, sınıf yapıları ve veri akış diyagramları için:
- 📖 [architecture_common.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/common/architecture_common.md)
- 📊 [architecture_common.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/common/architecture_common.dot) (Graphviz DOT kaynağı)

---

## 🚀 Temel Özellikler

1. **Konfigürasyon Yükleyici (`config_loader`):** `agent.yaml` ve modül konfigürasyonlarını hiyerarşik olarak birleştirir ve önbelleğe alır.
2. **Model Politikası (`model_policy`):** Yerel (Ollama / `qwen3.5:9b`) ve bulut (Google AI Studio / `gemini-2.5-flash`) profillerini dinamik ve güvenli yönetir.
3. **Ollama URL Koruyucusu (`ollama_url`):** Döngüsel Gateway yönlendirmelerini engeller, bozuk adresleri otomatik düzeltir.
4. **Olay Dağıtıcı (`event_bus`):** Modüller arası tamponlu (bounded ring buffer) pub/sub mesajlaşma sağlar.
5. **Güvenli HTTP İstemcisi (`http_client`):** Zaman aşımı korumalı, circuit-breaker destekli mikroservis istemcisi.

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