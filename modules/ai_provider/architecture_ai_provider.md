# AI Provider Modülü Mimari ve Teknik Dokümantasyonu (Multi-Provider LLM Engine)

> **Modül:** `modules/ai_provider`  
> **Kapsam:** `xOllamaService.py`, `services/clients.py`, `services/chat.py`, `services/translator.py`, `services/tags.py`, `api/`, `models/sentry_schema.py`  
> **Tasarım Deseni:** Multi-Provider Factory, Priority Heap Scheduler, Resilient HTTP Client with Exponential Backoff, Pydantic Schema Validator  
> **Varsayılan Port:** `8099` (FastAPI REST & Streaming Server)  
> **Varsayılan Yerel Model:** `qwen3.5:9b` (Ollama) | **Bulut Yedek:** `gemini-2.5-flash` (Google AI Studio)

---

## 1. Genel Bakış ve Modül Sorumlulukları

`modules/ai_provider` (eski adıyla `ollama`), SentryBOT V5'in bilişsel zekâsını, metin üretimini, karar alma mekanizmasını ve araç çağrılarını (action calling) yöneten merkezi büyük dil modeli (LLM) servisidir. Modül, tek bir LLM motoruna bağımlı kalmamak üzere çoklu sağlayıcı (Multi-Provider) mimarisinde yeniden tasarlanmıştır.

Modülün temel sorumlulukları şunlardır:

1. **Yerel Ollama Yönlendirmesi & Devre Kesici:** Tüm canlı çıkarımlar kalıcı HTTP `requests.Session` kullanan `OllamaClient` üzerinden yürütülür (`think=False` ve zaman aşımı zorunlu). Geçici ağ/5xx hatalarında `_CircuitBreaker` açılarak ölü köprülerde gereksiz beklemeyi önler; devre dışı `GoogleAIStudioClient` uyumluluk stub'ı başlangıçta reddedilip Ollama'ya yönlendirilir.
2. **Öncelikli Çıkarım Zamanlayıcısı (`PriorityInferenceLock`):** `(priority, itertools.count(), threading.Event)` yığını ile aynı saat tikinde bile Deterministik FIFO ve `TypeError` korumalı öncelik sırası sunar.
3. **Yapılandırılmış Çıktı, SSE Akışı & Eylem Yönlendirme:** `/ollama/chat` `structured=True` olduğunda `SentryResponse.model_json_schema()` şemasını, `stream=True` olduğunda NDJSON/SSE token akışını kullanır; eylemleri `@gateway/...` çözümlemeli kalıcı `requests.Session` ile iletir.
4. **Thread-Safe Bellek, Kişilik & Model Paylaşımı:** `runtime["_lock"]` altındaki paylaşımlı bağlam `/persona/select`, `/model/add` ve `/runtime/num_predict` değişikliklerini anında `/chat` ve `/healthz`'e yansıtır; kişi adları path traversal doğrulamasından geçer.
5. **DRY Konfigürasyon & Çeviri Önbelleği (`OllamaTranslator`):** `config_loader.py` doğrudan `modules.common.config_loader.load_ai_provider_config()`'e delege eder (`single_model_mode` / `allowed_models` YAML destekli); `OllamaTranslator` kilit korumalı LRU `_cache`/`_detect_cache` kullanır.

---

## 2. Mimari ve Veri Akış Diyagramları

### 2.1 Sohbet Yaşam Döngüsü ve Sağlayıcı Seçim Akışı (Mermaid Flowchart)

```mermaid
flowchart TD
    classDef client fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fff;
    classDef route fill:#1e293b,stroke:#64748b,stroke-width:1px,color:#f8fafc;
    classDef logic fill:#065f46,stroke:#34d399,stroke-width:2px,color:#fff;
    classDef parse fill:#312e81,stroke:#818cf8,stroke-width:2px,color:#fff;
    classDef ext fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#fff;

    REQ["POST /ollama/chat\n{text, persona, priority}"]:::route --> SCHED["PriorityInferenceLock.acquire(priority)"]:::client
    SCHED --> CHAT_SVC["OllamaChatService.chat()"]:::logic
    
    CHAT_SVC --> MEM["ChatMemory (Son 6 Mesaj)"]:::logic
    CHAT_SVC --> PERSONA["PersonaLoader (sentry / glados)"]:::logic
    
    PERSONA --> BLD_PROMPT["Sistem İstemi + Geçmiş + Kullanıcı Girdisi"]:::logic
    BLD_PROMPT --> FACTORY["create_llm_client (Sağlayıcı Seçimi)"]:::client

    FACTORY -->|provider='google' (DISABLED=True)| FALLBACK["Router Fallback -> OllamaClient"]:::client
    FACTORY -->|provider='ollama'| OLLAMA_CLI["OllamaClient (Session + Breaker)"]:::client
    FALLBACK --> OLLAMA_CLI

    OLLAMA_CLI -->|HTTP POST /api/chat\n(stream/think=False/timeout)| OLLAMA_API["Ollama Daemon (:11434)"]:::ext
    OLLAMA_API --> RAW_RESP["Ham / Akış LLM Yanıtı"]:::client

    RAW_RESP --> PYDANTIC{"Pydantic JSON Ayrıştırma\n(SentryResponse)"}:::parse
    PYDANTIC -->|Geçerli JSON| STRUCT_OK["Yapılandırılmış Yanıt\n(thoughts, speech, actions)"]:::parse
    PYDANTIC -->|Geçersiz / Düz Metin| REGEX_FALLBACK["extract_llm_tags (Regex Fallback)"]:::parse

    STRUCT_OK --> APPLY_CHK{"apply_actions = True?"}:::logic
    REGEX_FALLBACK --> APPLY_CHK

    APPLY_CHK -->|Evet| FWD["Action Forwarder -> POST /actions/execute"]:::ext
    APPLY_CHK -->|Hayır| RESP_OUT["API Yanıtı Döndür (JSON / Stream)"]:::route
    FWD --> RESP_OUT
```

---

### 2.2 Öncelikli Çıkarım Sıralaması ve Preemption (Mermaid Sequence)

```mermaid
sequenceDiagram
    autonumber
    actor Background as Autonomy / Idle Worker
    actor User as Kullanıcı (Sesli Komut)
    participant Lock as PriorityInferenceLock
    participant Client as OllamaClient / GoogleClient
    participant LLM as LLM Engine (:11434 / Cloud)

    Note over Background,Lock: Arka planda otonom düşünce süreci başlar (Öncelik = 2)
    Background->>Lock: acquire(priority=2)
    Lock-->>Background: Kilit Verildi (İşlem Aktif)
    Background->>Client: chat(messages=[...], priority=2)
    Client->>LLM: POST /api/chat

    Note over User,Lock: KULLANICI KONUŞTU (Öncelik = 0 - Acil)
    User->>Lock: acquire(priority=0)
    Note over Lock: Kilit meşgul; Kullanıcı isteği kuyruğun en önüne (heap index 0) yerleşir!
    
    LLM-->>Client: Arka Plan Yanıtı Bitti
    Client-->>Background: İşlem Tamamlandı
    Background->>Lock: release()

    Note over Lock: Kilit serbest kalınca kuyruktaki Öncelik 0 anında uyandırılır
    Lock-->>User: Öncelik 0 Kilidi Devraldı (0ms Gecikme)
    User->>Client: chat(messages=[Kullanıcı Sorusu], priority=0)
    Client->>LLM: POST /api/chat
    LLM-->>Client: Kullanıcı Yanıtı
    Client-->>User: Yanıt Gönderildi
    User->>Lock: release()
```

---

## 3. Sınıf, Fonksiyon ve Metot Seviyesi Teknik Referans

### 3.1 `services/clients.py` (Sağlayıcı İstemcileri ve Kuyruk)

```python
class LLMClientProtocol(Protocol):
    model: str
    def chat(self, messages: List[Dict[str, str]], format: Optional[Any] = None, *, options: Optional[Dict[str, Any]] = None, model: Optional[str] = None) -> Dict[str, Any]: ...
    def create_model(self, name: str, modelfile: str) -> bool: ...
    def pull_model(self, name: str) -> bool: ...
    def list_models(self) -> List[str]: ...
```

#### `PriorityInferenceLock`
Öncelik tabanlı çıkarım kuyruğu yönetir:
- `acquire(priority: int = 1)`: Context manager (`with priority_lock.acquire(priority):`).
  - `priority = 0`: Sesli kullanıcı komutu (En yüksek öncelik).
  - `priority = 1`: Standart sohbet / REST sorgusu.
  - `priority = 2`: Arka plan içsel düşünceleri (Düşük öncelik).
  - **İç Mantık:** Dahili `heapq` kullanarak `(priority, itertools.count(), threading.Event)` üçlülerini tutar; aynı zaman dilimindeki eşzamanlı isteklerde deterministik FIFO sağlar.

#### `OllamaClient` & `_CircuitBreaker`
- Tek birleşik HTTP `requests.Session` yolu üzerinden çalışır (`think=False`, zorunlu `request_timeout`); yedekli `ollama.Client` çift çıkarım yolu kaldırılmıştır.
- `chat(...)` & `chat_stream(...)`: NDJSON token akışı, 1 geçici bağlantı tekrar denemesi ve `cb_failure_threshold`/`cb_recovery_timeout_s` parametreleriyle `CircuitOpenError` hızlı devresi sağlar.

#### `GoogleAIStudioClient` (`services/google_ai_client.py`)
- `DISABLED = True`: Devre dışı uyumluluk stub'ıdır (`ProviderDisabledError` yükseltir); `router.py` başlangıçta yerel Ollama'ya düşer, `health.py` `provider_disabled` raporlar.

#### `create_llm_client(cfg: Dict[str, Any]) -> Tuple[LLMClientProtocol, str]`
- `cfg["llm"]["provider"]` değerini inceler (`"google"` veya `"ollama"`).
- Google seçilmişse ve geçerli bir API anahtarı varsa `GoogleAIStudioClient` döner.
- Anahtar yoksa veya Ollama seçilmişse `OllamaClient` döner. Başlatma hatası durumunda otomatik olarak Ollama fallback'e geçer.

---

### 3.2 `services/chat.py` (`OllamaChatService`)

- `__init__(client: LLMClientProtocol, persona_name: str = "sentry", max_history: int = 6, use_persona_as_model: bool = False, num_predict: int = 100)`:
  - `max_history`: Çok turlu sohbet hafızasında tutulacak en fazla kullanıcı-asistan mesaj çifti sayısı (bellek şişmesini önler).
- `chat(user_text: str, system_override: Optional[str] = None, priority: int = 1, format: Optional[Any] = None) -> Dict[str, Any]`:
  - Kişilik sistem metnini ve konuşma geçmişini birleştirir.
  - İstemciye `chat()` çağrısı yapar.
  - Asistan cevabını belleğe kaydeder (`add_interaction`).
  - Gelen yanıtı yapılandırılmış eylemler (`SentryResponse`) için hazırlar.

---

### 3.3 `services/translator.py` (`OllamaTranslator`)

- `detect_language(text: str) -> str`:
  - Türkçe özel harfler (`ğ, ü, ş, ı, ö, ç`) ve Türkçe sık kullanılan ek/sözcük frekansına göre `"tr"` veya `"en"` tespiti yapar.
- `translate(text: str, source_lang: str, target_lang: str) -> str`:
  - Kaynak ve hedef dil aynıysa doğrudan metni döner.
  - Çift yönlü bellek içi `_cache` sözlüğünde arar; yoksa LLM'e düşük `num_predict` ve yüksek sıcaklık kısıtlamasıyla çeviri yaptırır.

---

### 3.4 `models/sentry_schema.py` (Pydantic Modelleri)

```python
class RobotAction(BaseModel):
    type: str
    attrs: Dict[str, Any] = Field(default_factory=dict)

class SentryResponse(BaseModel):
    text: str
    thoughts: str
    actions: List[RobotAction] = Field(default_factory=list)
```

---

## 4. REST API Endpoint Tablosu (`:8099`)

Tüm API rotaları varsayılan olarak `/ollama` öneki altındadır:

| Metot | Uç Nokta | Açıklama | Parametreler / Gövde |
|---|---|---|---|
| `GET`/`POST` | `/ollama/chat` | Öncelikli sohbet (`structured=true` -> `SentryResponse`, `stream=true` -> SSE) | `?query=...&structured=false&stream=false` |
| `POST` | `/ollama/translate` | TR/EN köprü çevirisi | `?text=...&source_lang=auto&target_lang=en` |
| `POST` | `/ollama/runtime/num_predict` | Dinamik token üst sınırını günceller (`min 48`) | `{"num_predict": 120}` |
| `GET` | `/ollama/healthz` | LLM motoru, model ve `circuit_breaker` durumu | `{"ok": true, "provider": "ollama", "model_available": true}` |
| `GET` | `/ollama/persona`, `/ollama/personas` | Aktif kişiliği ve diskteki kişilik listesini döner | `{"ok": true, "items": ["sentry"]}` |
| `POST` | `/ollama/persona/select` | Güvenli ad doğrulamasıyla aktif kişiliği seçer | `?name=sentry` |
| `POST` | `/ollama/persona/create_from_url` | `http(s)` URL'den kişilik metni indirir | `?name=...&url=https://...` |
| `GET` | `/ollama/models` | Yüklü Ollama modellerini ve aktif modeli listeler | `{"ok": true, "items": [...], "active": "..."}` |
| `POST` | `/ollama/model/add`, `/ollama/warmup` | Yeni model çeker (`pull`) veya önyükler | `?name=qwen3.5:9b&set_default=true` |

---

## 5. Konfigürasyon Referansı (`config.yml` ve `agent.yaml`)

```yaml
# Sağlayıcı ve Model Tercihleri
llm:
  provider: "ollama"           # "ollama" veya "google" / "google_ai_studio"
  single_model_mode: true      # Tek bir temel model üzerinden sistem promptu ile kişilik yönetimi
  use_persona_models: false    # Her kişilik için ayrı türetilmiş model aransın mı?

# Yerel Ollama Motoru Ayarları
ollama:
  base_url: "http://127.0.0.1:11434"
  model: "qwen3.5:9b"
  num_predict: 120             # Maksimum token üretim sınırı
  temperature: 0.6
  request_timeout: 45.0

# Google AI Studio (Bulut / Fallback) Ayarları
google_ai_studio:
  api_key: ""                  # Ortam değişkeni GOOGLE_API_KEY ile de beslenebilir
  model: "gemini-2.5-flash"
  request_timeout: 30.0

# Kişilik ve Çeviri Ayarları
persona:
  default: "sentry"
  dir: "modules/ai_provider/config/personalities"

actions:
  endpoint: "http://127.0.0.1:8080/actions/execute"
  timeout: 1.5
  default_apply: true

translation:
  enabled: true
  bridge_language: "en"
```
