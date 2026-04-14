# State Manager Modülü Mimarisi

State Manager modülü (`modules/state_manager`), SentryBOT platformundaki birbiriyle izole çalışan mikroservislerin (Vision, Speech, Autonomy, Arduino vs.) ortak durum (global state) verilerini, örneğin anlık pil seviyesi, genel duygu (emotion) durumu, kilit/donma bayraklarını sakladığı, dağıtık sistemlerdeki "Redis" benzeri in-memory Data Store yapısıdır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Diğer tüm modüller bu servise GET/POST atarak durumu yazar veya sorgular.

```mermaid
flowchart TD
    %% Veri Yazma (SET)
    subgraph Update Flow [Durum Güncelleme İşlemi POST]
        direction TB
        REQ_UPDATE([POST /set/emotions <br> veya /set/battery]) --> PARSE_PAYLOAD(JSON Body Al)
        
        PARSE_PAYLOAD --> VALIDATE_PAYLOAD{"Anahtarlar <br> Geçerli mi?"}
        
        VALIDATE_PAYLOAD -- Hayır --> RET_ERR_U([Hata Döndür])
        VALIDATE_PAYLOAD -- Evet --> MUTEX_LOCK(Kilit Al - Thread Safe)
        
        MUTEX_LOCK --> MERGE_DICT[Store İçindeki Dictionary'e <br> Yeni Veriyi Merge Et] --> MUTEX_REL(Kilidi Bırak)
        
        MUTEX_REL --> TRIG_PUB_SUB{"Değişim Bildirimi <br> Aboneleri Var mı?"}
        TRIG_PUB_SUB -- Evet --> NOTIFY_SUBS(Abonelere Event Pushing) --> RET_OK_U([Başarılı])
        TRIG_PUB_SUB -- Hayır --> RET_OK_U
    end
    
    %% Veri Okuma (GET)
    subgraph Read Flow [Durum Okuma İşlemi GET]
        direction TB
        REQ_READ([GET /get/emotions <br> veya /state]) --> PARSE_QRY(Query Parametresi Al <br> Varsa Sadece Onu Ver)
        
        PARSE_QRY --> GET_LOCK[Kilit Al] --> CLONE_DAT[Kopya Oluştur <br> copy.deepcopy] --> UNLOCK[Kilidi Bırak]
        
        UNLOCK --> RET_JSON([Seçili State JSON'ı Dön])
    end
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    StateManager ||--o{ AutonomyBrain : written_by
    StateManager ||--o{ InteractionsEngine : read_by
    StateManager ||--o{ TelemetryService : read_by

    StateManager {
        string store_key
        string store_value
    }
    AutonomyBrain {
        string emotion_patch
        string state_namespace
    }
    InteractionsEngine {
        string read_key
        bool needs_freeze_flag
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Thread/Concurrency (Eşzamanlılık) Kilidi**
   - Gateway aynı anda 10 farklı module API hizmeti verirken (aynı anda hem Telemetry veriyi okuyor, hem de Autonomy veriyi düzeltiyor olabilir). Python dictionary'leri thread-safe olmadığından, her okuma ve yazma kararı önce `threading.Lock()` alır (`with self.store_lock:`). Aksi takdirde robot state bozulması "Race Condition" yaşar.
   - **`if`** Okuma ise, kilit anında tüm sözlüğün derin kopyası oluşturulup kilitten çıkılır (diğer thread'leri bekletmemek için).
2. **Varsayılan Değerler ve Kısmi Güncelleme (Partial Merge)**
   - API'ye (örneğin `/set/emotions`) sadece `{"happiness": 90}` gelirse;
   - Sistem **`if`** mevcut bir "emotions" anahtarı varsa öncelikle bunu alır `{"fear":10, "curiosity":50...}`, üzerine sadece `happiness`'i yazar, geri kalanı korur. (Komple ezme/overwrite yapmaz). Sonrasında kaydeder.
   - Tüm yazılım parçaları kararlarını almadan önce (Örn: Vision kişi selamlarken "Robotun modu uygun mu?") önce bu servisi sorar. Yorgunsa (`energy < 20`) selamlama iptal edilebilir.
