# SentryBOT V5 — AI Provider Modülü (`modules/ai_provider`)

SentryBOT V5'in merkezi büyük dil modeli (LLM) ağ geçidi ve bilişsel çıkarım servisidir. Yerel/uzak Ollama çıkarımı, öncelik kuyruğu, çok turlu sohbet belleği, TR/EN çeviri köprüsü ve yapılandırılmış eylem (action calling) entegrasyonunu yürütür (`GoogleAIStudioClient` uyumluluk stub'ı devre dışıdır ve başlangıçta güvenli biçimde Ollama'ya yönlendirilir).

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
│   ├── router.py                    # Ana API Montajı, Kilitli Runtime Paylaşımı & Sağlayıcı Fallback
│   ├── chat_routes.py               # /ollama/chat (stream/structured), /ollama/translate, /ollama/runtime/num_predict
│   ├── health.py                    # /ollama/healthz (Model & Circuit Breaker Probu)
│   ├── persona_routes.py            # /ollama/persona, /ollama/personas, /ollama/persona/select, /ollama/persona/create_from_url
│   └── models_routes.py             # /ollama/models, /ollama/model/add, /ollama/warmup
├── services/                        # Temel İş Mantığı ve İstemciler
│   ├── clients.py                   # create_llm_client, OllamaClient (Session/Breaker/Stream), PriorityInferenceLock
│   ├── google_ai_client.py          # Devre Dışı Google AI Studio Uyumluluk Stub'ı (ProviderDisabledError)
│   ├── chat.py                      # Thread-Safe OllamaChatService (Chat & chat_stream)
│   ├── translator.py                # Thread-Safe OllamaTranslator (TR/EN Çift Yönlü Çeviri Köprüsü)
│   ├── tags.py                      # Regex Action Tag Ayrıştırıcısı
│   └── memory.py                    # RLock Korumalı Konuşma Geçmişi Önbelleği
└── models/                          # Pydantic Şemaları
    └── sentry_schema.py             # SentryResponse, RobotAction Yapılandırılmış Çıktı (`structured=True`)
```

---

## 🛠️ Servisi Çalıştırma

### Bağımsız API Sunucusu Olarak Başlatma
```bash
python -m modules.ai_provider.xOllamaService
# Varsayılan: 127.0.0.1:8099 adresinde FastAPI sunucusunu açar.
# LAN için server.host: 0.0.0.0 veya OLLAMA_SERVICE_HOST=0.0.0.0.
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

### 1. Sohbet, Akış (SSE) ve Eylem Yürütme (`Chat`)
```bash
curl -X POST "http://127.0.0.1:8099/ollama/chat?query=Bana%20bak%20ve%20selam%20ver&structured=true&apply_actions=true"
# Akış (SSE) için: ?query=Merhaba&stream=true
```

### 2. Sağlık ve Devre Kesici Kontrolü (`Healthz`)
```bash
curl -X GET http://127.0.0.1:8099/ollama/healthz
```

### 3. Aktif Kişiliği Değiştirme
```bash
curl -X POST "http://127.0.0.1:8099/ollama/persona/select?name=sentry"
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