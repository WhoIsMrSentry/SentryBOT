# Config Center Modülü Mimarisi

Config Center modülü (`modules/config_center`), sistemdeki tüm `config.yml` ve `.json` yapılandırma dosyalarının okunup, doğrulanıp (validate) anlık olarak değiştirilmesini sağlayan yönetim panelinin arka yüzüdür.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Okuma Akışı
    REQ_GET("GET /config") --> READ_DISK("config.yml Oku")
    READ_DISK --> VALID_YAML{"YAML Geçerli mi?"}
    VALID_YAML -- "Hayır" --> LOAD_BACKUP("Backup Yükle")
    VALID_YAML -- "Evet" --> RET_CFG("JSON Olarak<br>Arayüze Dön")
    LOAD_BACKUP --> RET_CFG
    
    %% Yazma & Rollback Akışı
    REQ_POST("PUT /config/set (?dry_run)") --> PARSE_NEW("YAML safe_load & Mapping Kontrolü")
    PARSE_NEW --> VALID_SCHEMA{"Geçerli mi?"}
    
    VALID_SCHEMA -- "Hata" --> RET_ERR("HTTP 400 Döndür")
    VALID_SCHEMA -- "dry_run=true" --> RET_DRY("Yazmadan Özet Dön")
    VALID_SCHEMA -- "Evet" --> SAVE_YAML("Son 5 .bak Koru + os.replace Atomik Yaz")
    
    SAVE_YAML --> HOT_RELOAD("clear_agent_config_cache + apply_module_yaml")
    HOT_RELOAD --> RET_OK("Başarılı")

    REQ_RB("POST /config/rollback") --> PICK_BAK("Son .bak-* Yedeğini Seç")
    PICK_BAK --> SAVE_YAML
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    ConfigCenter ||--o{ FileSystem : reads_writes
    ConfigCenter ||--o{ AllModules : triggers_hot_reload

    ConfigCenter {
        string config_path
        string schema_version
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Şema Doğrulaması (Validation)**
   - Pydantic modelleri devreye girer. **`if`** `volume` parametresi (0-100) aralığı yerine "yüz" veya `-50` gelmişse, sistem bunu `config.yml` dosyasına yazmayı reddeder. Böylece botun başlamama riski ortadan kalkar.
2. **Hot Reload vs Restart (Soğuk/Sıcak Yenileme)**
   - Bazı ayarlar değiştikten sonra anında geçerli olur (Örn: konuşma hızı, otonomi algı hassasiyeti). Bunlar için ram üzerindeki sınıfların property değerleri ezilir (`Hot-reload`).
   - Fakat seri haberleşme portu, baudrate, kamera backend'i (OpenCV -> PiCamera) gibi derin değişiklikler varsa, **`if`** `key in REQUIRED_RESTART_KEYS`: Gateway'e yeniden başlama (restart) sinyali atılır.
