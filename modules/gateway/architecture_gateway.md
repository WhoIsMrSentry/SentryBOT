# Gateway Modülü Mimarisi

Gateway modülü (`modules/gateway`), SentryBOT'un tüm mikroservislerini tek bir FastAPI uygulamasında birleştiren merkezi başlatıcı (bootstrap) katmanıdır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Aşağıdaki diyagram, uygulamanın nasıl başlatıldığını ve konfigürasyondaki `include` bayraklarının (if/else) nasıl değerlendirildiğini gösterir:

```mermaid
flowchart TD
    %% Başlangıç
    START([run_robot.py]) --> INIT_LOG["init_logging_<br> Hata Yoksayılır"]
    INIT_LOG --> LOAD_CFG["load_config: <br> config.yml okuma"]
    LOAD_CFG --> CREATE_APP[create_app]

    %% create_app iç akışı
    subgraph create_app [FastAPI Oluşturma]
        direction TB
        APP_INIT[FastAPI Uygulaması Başlat] --> STATE_INIT[app.state.started empty]
        STATE_INIT --> CALL_BOOTSTRAP[bootstrap app, cfg]
        CALL_BOOTSTRAP --> CORE_API[Core API /status mount]
    end
    
    CREATE_APP --> APP_INIT

    %% Bootstrap Akışı
    subgraph Bootstrap [Modül Yükleme Karar Ağacı]
        direction TB
        B_START([bootstrap başlar]) --> READ_INC{"cfg.include var mı?"}
        READ_INC -- Hayır --> B_END([Döndür: started list])
        READ_INC -- Evet --> CHK_ARDUINO{"include.arduino == true?"}
        
        %% Arduino
        CHK_ARDUINO -- Evet --> TRY_ARD[arduino._include_arduino]
        TRY_ARD --> CATCH_ARD{"Hata var mı?"}
        CATCH_ARD -- Evet --> LOG_ARD[warning: module failed] --> CHK_VIS
        CATCH_ARD -- Hayır --> ADD_ARD[started arduino True] --> CHK_VIS
        CHK_ARDUINO -- Hayır --> CHK_VIS{"include.vlm_bridge == true?"}

        %% VLM Bridge
        CHK_VIS -- Evet --> TRY_VIS[vlm._include_vlm_bridge]
        TRY_VIS --> CATCH_VIS{"Hata var mı?"}
        CATCH_VIS -- Evet --> LOG_VIS[warning: module failed] --> CHK_AUTO
        CATCH_VIS -- Hayır --> ADD_VIS[started vlm_bridge True] --> CHK_AUTO
        CHK_VIS -- Hayır --> CHK_AUTO{"include.autonomy == true?"}

        %% Autonomy (Diğerleri benzer mantıkta olduğu için temsilidir)
        CHK_AUTO -- Evet --> TRY_AUTO[autonomy._include_autonomy]
        TRY_AUTO --> CATCH_AUTO{"Hata var mı?"}
        CATCH_AUTO -- Evet --> LOG_AUTO[warning: module failed] --> CHK_OTHER
        CATCH_AUTO -- Hayır --> ADD_AUTO[started autonomy ServiceClient] --> CHK_OTHER
        CHK_AUTO -- Hayır --> CHK_OTHER{"Diğer 20+ Modül <br> neopixel, speak, vb."}

        %% Diğerleri
        CHK_OTHER --> B_END
    end

    CALL_BOOTSTRAP --> B_START
    B_END --> CORE_API
    CORE_API --> RUN_UVICORN([uvicorn.run host:port])
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

Gateway yapısal olarak veri işlemez, modüllerin rotalarını API ağacına ekler. Veri bağlantıları şöyledir:

```mermaid
erDiagram
    Gateway ||--o{ ModuleRouter : mounts
    ModuleRouter ||--|| ArduinoService : instantiates
    ModuleRouter ||--|| AutonomyService : instantiates
    ModuleRouter ||--|| VlmService : instantiates
    AutonomyService }|..|{ ArduinoService : references
    VlmService }o..o{ ArduinoService : optional_calls

    Gateway {
        string started_services
        string config_snapshot
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **`create_app(config_path)`**
   - **`if`** `config_path` verilmemişse, varsayılan `modules/gateway/config/config.yml` kullanılır.
   - **`try`** modül başlatma (`bootstrap`), **`except`** hatayı yut (uygulama çökmesin).
2. **`bootstrap(app, cfg)`**
   - **Yardımcı Fonksiyon `_try(fn, name)`**: 
     - İçine gönderilen lambda fonksiyonu (modül router'ını bağlayan kod) çalıştırılır.
     - **`except Exception`**: Eğer modül içindeki bir import veya bağlanma hatası (ör. donanım eksikliği) başlatmayı engellerse, sistemi durdurmaz (`logger.warning`), uygulamanın kalanı çalışmaya devam eder.
    - Modül yükleme öncelik sırası: Güvenli olması açısından donanım iletişimi (`arduino`) en önce, üzerine inşa edilen modüller (`autonomy`, `vlm`) daha sonra eklenir.
