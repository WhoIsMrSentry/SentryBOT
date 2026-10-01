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

1. **Çoklu Sağlayıcı ve Geri Çekilme (Multi-Provider & Fallback):** Yerel Ollama sunucusunu (`http://127.0.0.1:11434`) birincil motor olarak koşturur. Bulut profili seçildiğinde veya yerel kaynaklar yetersiz kaldığında Google AI Studio (Gemini) REST API'sine şeffaf geçiş yapar; bulut anahtarı geçersizse otomatik olarak yerel Ollama motoruna geri döner.
2. **Öncelikli Çıkarım Zamanlayıcısı (`PriorityInferenceLock`):** Kullanıcının sesli komutları (Öncelik 0 - yüksek), normal sohbet istekleri (Öncelik 1 - orta) ve robotun boşta çalışırken ürettiği içsel/otonom düşünceleri (Öncelik 2 - düşük) bir öncelik kuyruğunda (`heapq`) sıraya dizer. Kullanıcı konuştuğunda arka plan otonom düşüncelerinin kullanıcı yanıtını geciktirmesini engeller.
3. **Yapılandırılmış Çıktı ve Eylem Yürütme (Structured Actions & Tag Extraction):** Modelden dönen metinleri `SentryResponse` Pydantic şemasıyla doğrular; şema dışı veya kısmi JSON yanıtlarında düzenli ifadelerle (`extract_llm_tags`) XML benzeri etiketleri (`<action>`, `<emotion>`) ayrıştırır ve Gateway üzerindeki eylem motoruna (`/actions/execute`) iletir.
4. **Kişilik ve Karakter Yönetimi (Persona Management):** `sentry` ve `glados` gibi kişilik tanımlarını diskten dinamik olarak okur, sistem komutlarına enjekte eder ve istendiğinde tek komutla yeni Ollama modelleri derler (`create_model`).
5. **Çift Yönlü Çeviri Köprüsü (`OllamaTranslator`):** Türkçe ve İngilizce arasındaki dil ayrımını sezgisel olarak tespit eder, istemleri gerektiğinde modele uygun dile çevirir ve bellek içi önbellek (`_cache`) ile gecikmesiz çalışır.

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

    FACTORY -->|provider='google' & valid_key| GOOGLE_CLI["GoogleAIStudioClient (Gemini-2.5-Flash)"]:::client
    FACTORY -->|provider='ollama' veya fallback| OLLAMA_CLI["OllamaClient (qwen3.5:9b)"]:::client

    GOOGLE_CLI -->|REST generateContent| GOOGLE_API["Google AI Studio API"]:::ext
    OLLAMA_CLI -->|HTTP POST /api/chat\n(Retry: 2 Deneme)| OLLAMA_API["Yerel Ollama Daemon (:11434)"]:::ext

    GOOGLE_API --> RAW_RESP["Ham LLM Yanıtı"]:::client
    OLLAMA_API --> RAW_RESP

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
  - **İç Mantık:** Dahili `heapq` kullanarak sıralanmış `(priority, timestamp, threading.Event)` çiftlerini tutar. Kilit boşa çıktığında en düşük sayısal değerli (en yüksek öncelikli) olayı tetikler.

#### `OllamaClient`
- `__init__(base_url: str, model: str, request_timeout: float = 60.0)`:
  - `base_url`: `normalize_ollama_url()` ile biçimlendirilir. Gateway self-URL'leri (`:8080`) döngü kilitlenmelerini önlemek amacıyla kesinlikle reddedilir.
- `chat(messages, format=None, options=None, model=None, priority=1) -> Dict[str, Any]`:
  - **Dirençli Yeniden Deneme (Resilient Retry):** Ağ hatası (`requests.exceptions.ConnectionError`) veya zaman aşımında 200 ms bekleyip 1 kez daha dener (toplam 2 deneme).
  - Yanıttan `content` metnini ayıklar ve standart `{"message": {"content": ...}, "raw": ...}` formatında döner.
- `is_alive(timeout: float = 2.0) -> bool`: `/api/version` ve `/api/tags` uç noktalarını yoklayarak daimonun ayakta olduğunu doğrular.
- `list_models() -> List[str]`: Ollama'da yüklü model adlarını listeler.
- `pull_model(name: str) -> bool`: Model indirme isteği atar (`/api/pull`).
- `create_model(name: str, modelfile: str) -> bool`: Özel Modelfile içeriği ile model derler (`/api/create`).

#### `GoogleAIStudioClient` (`services/google_ai_client.py`)
- `_sanitize_google_api_key(raw_value: Any) -> str`: `your-api-key`, `changeme`, `replace_me` gibi yer tutucu anahtarları tespit edip reddeder.
- `chat(...)`: Google AI Studio `v1beta/models/{model}:generateContent` REST uç noktasına istek atar. Gelen JSON içerisindeki `candidates[0].content.parts[0].text` bloğunu standart `message.content` yapısına uyarlar.

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
class ActionCall(BaseModel):
    name: str                   # Eylem adı: "nod_head", "look_around", "change_face"
    parameters: Dict[str, Any] = Field(default_factory=dict)

class SentryResponse(BaseModel):
    thoughts: str = ""          # Robotun içsel akıl yürütmesi (hoparlörden okunmaz)
    speech: str = ""            # Robotun seslendireceği nihai yanıt
    emotion: str = "neutral"    # Yüz ifadesi: "happy", "curious", "sad", "angry"
    actions: List[ActionCall] = Field(default_factory=list)
```

---

## 4. REST API Endpoint Tablosu (`:8099`)

Tüm API rotaları varsayılan olarak `/ollama` öneki altındadır:

| Metot | Uç Nokta | Açıklama | Parametreler / Gövde |
|---|---|---|---|
| `POST` | `/ollama/chat` | Öncelikli sohbet ve çıkarım | `{"text": "Merhaba", "persona": "sentry", "priority": 0, "apply_actions": true}` |
| `POST` | `/ollama/generate` | Geçmişsiz tek seferlik metin üretimi | `{"prompt": "Özetle...", "model": "qwen3.5:9b"}` |
| `POST` | `/ollama/stream` | Token akışı (SSE streaming) | `{"text": "Detaylı anlat...", "priority": 1}` |
| `GET` | `/ollama/health` | LLM motoru ve model doğruluk kontrolü | Yanıt: `{"status": "ok", "provider": "ollama", "model_available": true}` |
| `GET` | `/ollama/persona` | Aktif ve yüklü kişilik listesi | Yanıt: `{"active": "sentry", "available": ["sentry", "glados"]}` |
| `POST` | `/ollama/persona/set` | Aktif kişiliği değiştirir | `{"persona": "glados"}` |
| `POST` | `/ollama/persona/create` | Yeni Modelfile derler | `{"name": "sentry_v2", "modelfile": "FROM qwen3.5:9b..."}` |
| `GET` | `/ollama/models` | Yüklü Ollama modellerini listeler | Yanıt: `{"models": ["qwen3.5:9b", "llama3.2:3b"]}` |
| `POST` | `/ollama/models/pull` | Yeni modeli yerel daemona indirir | `{"name": "qwen3.5:9b"}` |

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
