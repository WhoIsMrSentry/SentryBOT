# SentryBOT V5 — AI Provider Modülü (`modules/ai_provider`)

SentryBOT V5'in merkezi büyük dil modeli (LLM) ağ geçidi ve bilişsel çıkarım servisidir. Robotun akıl yürütme, doğal dil anlama, diyalog yönetimi, çoklu sağlayıcı (Ollama & Google AI Studio Gemini) desteği ve araç/eylem (action calling) entegrasyonunu yürütür.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

AI Provider servisi hem yerel Ollama motorunu hem de Google AI Studio Gemini API'sini destekler:

```bash
# Gerekli Python kütüphaneleri:
pip install requests fastapi uvicorn pydantic pyyaml
```

### 2. Yerel Modeli Hazırlama (Ollama)
SentryBOT varsayılan olarak **`qwen3.5:9b`** modelini kullanır:

```bash
# Ollama kurulu değilse: https://ollama.com
ollama pull qwen3.5:9b
```

---

## 📂 Dizin Yapısı

```
modules/ai_provider/
├── xOllamaService.py                # Servis Giriş Noktası & FastAPI Başlatıcı (:8099)
├── config_loader.py                 # agent.yaml ve Yerel YAML Yapılandırma Yükleyici
├── architecture_ai_provider.dot     # Graphviz Mimari Diyagram Kaynağı
├── architecture_ai_provider.svg     # Derlenmiş Vektörel Mimari Şema
├── architecture_ai_provider.md      # Kapsamlı Teknik & Sınıf Referansı
├── README.md                        # Bu doküman
├── api/                             # REST API Yönlendiricileri (Prefix: /ollama)
│   ├── router.py                    # Ana API Montajı ve Servis Yaşam Döngüsü
│   ├── chat_routes.py               # /ollama/chat, /ollama/generate, /ollama/stream
│   ├── health.py                    # /ollama/health (Model Doğruluk & Gecikme Probu)
│   ├── persona_routes.py            # /ollama/persona, /ollama/persona/set
│   └── models_routes.py             # /ollama/models, /ollama/models/pull
├── services/                        # Temel İş Mantığı ve İstemciler
│   ├── clients.py                   # create_llm_client, OllamaClient, PriorityInferenceLock
│   ├── google_ai_client.py          # Google AI Studio Gemini REST İstemcisi
│   ├── chat.py                      # OllamaChatService (Çok Turlu Sohbet & Bellek)
│   ├── translator.py                # OllamaTranslator (TR/EN Çift Yönlü Çeviri Köprüsü)
│   ├── tags.py                      # Regex Fallback XML/Tag Ayrıştırıcısı
│   └── memory.py                    # Konuşma Geçmişi Önbelleği
└── models/                          # Pydantic Şemaları
    └── sentry_schema.py             # SentryResponse, ActionCall Yapılandırılmış Çıktı
```

---

## 🛠️ Servisi Çalıştırma

### Bağımsız API Sunucusu Olarak Başlatma
```bash
python -m modules.ai_provider.xOllamaService
# Varsayılan: 0.0.0.0:8099 adresinde FastAPI sunucusunu açar.
```

---

## 💻 Python Kullanım Örnekleri

### 1. Fabrika Üzerinden İstemci Oluşturma ve Öncelikli Çıkarım
```python
from modules.ai_provider.services.clients import create_llm_client, _INFERENCE_SCHEDULER

config = {
    "llm": {"provider": "ollama"},
    "ollama": {"base_url": "http://127.0.0.1:11434", "model": "qwen3.5:9b"}
}

client, provider = create_llm_client(config)
print(f"Aktif Sağlayıcı: {provider}, Model: {client.model}")

# Öncelikli sohbet çağrısı (Öncelik 0: Acil Kullanıcı Komutu)
with _INFERENCE_SCHEDULER.acquire(priority=0):
    response = client.chat(
        messages=[{"role": "user", "content": "SentryBOT, durum raporu ver."}],
        options={"temperature": 0.5}
    )
    print("Yanıt:", response["message"]["content"])
```

### 2. Kişilik Destekli Sohbet Servisi
```python
from modules.ai_provider.services.chat import OllamaChatService
from modules.ai_provider.services.clients import create_llm_client

client, _ = create_llm_client({"llm": {"provider": "ollama"}})
chat_svc = OllamaChatService(client, persona_name="sentry", max_history=6)

reply = chat_svc.chat("Sen kimsin ve ne iş yaparsın?")
print("Asistan Yanıtı:", reply)
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Sohbet ve Eylem Yürütme (Chat)
```bash
curl -X POST http://127.0.0.1:8099/ollama/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bana bak ve selam ver.",
    "persona": "sentry",
    "priority": 0,
    "apply_actions": true
  }'
```

### 2. Sağlık ve Model Doğruluk Kontrolü (Health Probe)
```bash
curl -X GET http://127.0.0.1:8099/ollama/health
```

### 3. Aktif Kişiliği Değiştirme
```bash
curl -X POST http://127.0.0.1:8099/ollama/persona/set \
  -H "Content-Type: application/json" \
  -d '{"persona": "glados"}'
```

### 4. Yüklü Modelleri Listeleme
```bash
curl -X GET http://127.0.0.1:8099/ollama/models
```

---

## 🧪 Testleri Çalıştırma

Modüle ait tüm testleri (Google anahtar doğrulama, Ollama URL kontrolü, çevirici ve öncelik zamanlayıcısı testleri) çalıştırmak için:

```bash
pytest tests/modules/ai_provider -v
```

---

## 🔗 Detaylı Mimari Dokümantasyonu
- [architecture_ai_provider.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/ai_provider/architecture_ai_provider.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_ai_provider.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/ai_provider/architecture_ai_provider.dot): Graphviz formatında modüler alt sistem çizimi.
- [architecture_ai_provider.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/ai_provider/architecture_ai_provider.svg): Vektörel mimari şeması.