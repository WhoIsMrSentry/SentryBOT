# SentryBOT V5 — Gateway Modülü (`modules/gateway`)

SentryBOT V5'in tüm dış istemciler (Web Arayüzü, Mobil Panel, REST/SSE istemcileri) ve modüller arası dahili iletişim trafiğini tek bir çatı altında birleştiren merkezi ters vekili (reverse proxy) ve API ağ geçididir. Robotun üretim ortamında tek bir port (`:8080`) üzerinden kararlı ve güvenli hizmet vermesini sağlar.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install fastapi uvicorn requests pyyaml
```

### 2. Gateway'i Başlatma

```bash
# Gateway'i varsayılan 8080 portunda koşturma:
python -m modules.gateway.xGatewayService
```

---

## 📂 Dizin Yapısı

```
modules/gateway/
├── xGatewayService.py                # Merkezi FastAPI Uygulaması ve Başlatıcı (:8080)
├── url.py                            # Gateway Self-URL ve Loopback Döngü Koruması
├── config_loader.py                  # YAML Yapılandırma Yükleyici
├── architecture_gateway.dot          # Graphviz Mimari Diyagram Kaynağı
├── architecture_gateway.svg          # Derlenmiş Vektörel Mimari Şema
├── architecture_gateway.md           # Kapsamlı Teknik & Sınıf Referansı
├── README.md                         # Bu doküman
├── api/
│   └── router.py                     # Kök Sağlık ve Durum Uç Noktaları (/healthz, /status)
├── services/                         # Modüler Önyükleme (Bootstrapper) Katmanı
│   ├── bootstrap.py                  # Ana Orkestrasyon, Zamanlı boot_manifest ve Yaşam Döngüsü
│   ├── bootstrap_config.py           # mtime_ns Destekli agent.yaml Önbelleği ve Ortak Stub Yardımcısı
│   ├── bootstrap_hardware.py         # Donanım Modülleri Montajı (/arduino, /camera, /neopixel, /piservo)
│   ├── bootstrap_ai.py               # Yapay Zeka Modülleri Montajı (/ollama, /vlm, /speak, /speech, /wakeword)
│   ├── bootstrap_ops.py              # Platform Modülleri Montajı (/state, /scheduler, /config, /telemetry, /diagnostics)
│   ├── agent_core_binding.py         # from_config & İmza Tabanlı Agent Core Bağlantısı
│   └── agent_api_compat.py           # Asenkron Ollama Araç Köprüsü & Uyumluluk Şimi (/agent/*, /api/agent/*)
```

---

## Güvenlik ve Gözlemlenebilirlik

- **Yetki Kontrolü (`X-API-Key`):** `/config`, `/ota`, `/scheduler/jobs` ön ekleri yalnızca `security.admin_keys` içindeki anahtarlarla yetkilendirilir (`X-Role: admin` başlığı tek başına yetki yükseltmez).
- **Bellek-İçi Sağlık & Hazırlık (`/health`, `/healthz`, `/readyz`):** Modüllerden doğrudan bellek içi `.health()` / `.status()` / `.is_running()` probu okunur (döngüsel loopback HTTP yok). `GET /readyz` her modülün açılış süresini (`duration_ms`), durumunu (`active` / `stub` / `disabled` / `error`) ve en yavaş modülü (`slowest_module`) döner.

---

## 🛠️ Modül Montaj Bayrakları (`include.*`)

Gateway, `config/agent.yaml` içerisindeki bayraklara göre servisleri çalışma zamanında dinamik olarak bağlar:

| Bayrak | Montaj Yolu | Açıklama |
|---|---|---|
| `include.camera` | `/camera` | Kamera servisi (IMX500, RTSP) |
| `include.arduino` | `/arduino` | Seri mikrodenetleyici donanım HAL |
| `include.ollama` | `/ollama` | LLM yapay zekâ servisi (Yerel Ollama / Gemini) |
| `include.voice` | `/speak`, `/speech` | Konuşma sentezi (TTS) ve tanıma (STT) |
| `include.visual_output` | `/oled_faces`, `/neopixel` | OLED yüz ifadeleri ve RGB LED halkası |
| `include.vlm` | `/vlm` | Çok modlu görme köprüsü |
| `include.memory` | `/memory` | Epizodik ve anlamsal bilişsel bellek |
| `include.agent_core` | `/agent`, `/chat` | Merkezi bilişsel ajan orkestratörü |

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Sistem Sağlık ve Aktif Modül Kontrolü
```bash
curl -X GET http://127.0.0.1:8080/healthz
```

### 2. Doğrudan Ajanla Sohbet (/chat)
```bash
curl -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Merhaba Sentry, devriye durumunu bildir."}'
```

### 3. Kamera Görüntüsü Alma
```bash
curl -X GET http://127.0.0.1:8080/camera/capture --output snapshot.jpg
```

### 4. Robotu Konuşturma (/speak/say şimi üzerinden)
```bash
curl -X POST http://127.0.0.1:8080/speak/say \
  -H "Content-Type: application/json" \
  -d '{"text": "Sistemler hazır.", "tone": "happy"}'
```

---

## 🧪 Testleri Çalıştırma

Gateway önyükleme, dinamik montaj ve URL koruma testlerini çalıştırmak için:

```bash
pytest tests/modules/gateway -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_gateway.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/gateway/architecture_gateway.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_gateway.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/gateway/architecture_gateway.dot): Graphviz formatında modüler ağ geçidi çizimi.
- [architecture_gateway.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/gateway/architecture_gateway.svg): Vektörel mimari şeması.