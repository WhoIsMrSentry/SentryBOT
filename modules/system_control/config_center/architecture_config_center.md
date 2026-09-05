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
    
    %% Yazma Akışı
    REQ_POST("POST /config") --> PARSE_NEW("Gelen JSON'ı Parse Et")
    PARSE_NEW --> VALID_SCHEMA{"Pydantic Şema<br>Doğrulaması?"}
    
    VALID_SCHEMA -- "Hata" --> RET_ERR("Hata Döndür:<br>Geçersiz Format")
    VALID_SCHEMA -- "Başarılı" --> SAVE_YAML("config.yml'e Yaz")
    
    SAVE_YAML --> RESTART_REQ{"Restart<br>Gerekiyor mu?"}
    RESTART_REQ -- "Evet" --> TRIG_RST("Modülü/Sistemi<br>Yeniden Başlat")
    RESTART_REQ -- "Hayır" --> HOT_RELOAD("Hafızadaki Objeyi<br>Güncelle (Hot-Reload)")
    
    TRIG_RST --> RET_OK("Başarılı")
    HOT_RELOAD --> RET_OK
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
