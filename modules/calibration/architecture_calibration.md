# Calibration Modülü Mimarisi

Calibration modülü (`modules/calibration`), robotun fiziksel eklentilerini (özellikle servolarını) ayarlamak ve bu ayarlamaları kalıcı hafızaya (EEPROM veya JSON) kaydetmekten sorumludur. Genellikle web üzerinden veya Arduino boot evresinde tetiklenir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

```mermaid
flowchart TD
    %% Kalibrasyon Modu Başlatma
    START(Kalibrasyon Modu İsteği) --> GET_REQ(POST /calibration/start)
    
    GET_REQ --> CHK_STATE{Robot Hareket<br>Halinde mi?}
    
    CHK_STATE -- Evet --> RET_BUSY(Hata: Önce robotu durdurun)
    CHK_STATE -- Hayır --> SET_STATE(Mod = CALIBRATION_MODE)
    
    %% Çekirdek Döngü
    subgraph Kalibrasyon Döngüsü
        direction TB
            SET_STATE --> RECV_CMD(İstemciden Servo Açısı Al Örn: pan: 95)
            RECV_CMD --> SEND_ARDU(Arduinoya Doğrudan İlet: set_servo id value)
        SEND_ARDU --> WAIT_USR{Kullanıcı Onayı?}
        
        WAIT_USR -- Hayır (Değiştir) --> RECV_CMD
        WAIT_USR -- Evet (Kaydet) --> SAVE_CONF
    end
    
    %% Kaydetme Döngüsü
    subgraph Kalıcı Hafıza
        direction TB
        SAVE_CONF(Yapılandırmayı Yaz) --> CHK_DEST{Hedef Neresi?}
        
        CHK_DEST -- EEPROM --> SEND_EEP(Arduino EEPROM<br>Write Komutu)
        CHK_DEST -- Raspberry Pi --> WRITE_JSON(config.yml / calib.json<br>Üzerine Yaz)
    end
    
    SEND_EEP --> RET_OK(Başarılı)
    WRITE_JSON --> RET_OK
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    CalibrationService ||--|| ArduinoSerial : controls
    CalibrationService ||--o{"ConfigManager : updates
    
    CalibrationService {
        start_matrix
        save_offsets"}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Güvenlik / Movement Lock**
   - **`if`** AutonomyBrain şu an aktif bir `ACT` döngüsü yürütüyorsa veya uyku modunda değilse, kalibrasyon istekleri robotun dengesini bozmamak için reddedilir.
2. **Kayıt Yeri Kararı**
   - Gelenekte IMU (Denge) offsetleri Arduino üzerindeki EEPROM'a donanım seviyesinde kaydedilir ki Raspberry Pi çökse bile Arduino ayarı saniyesinde okusun.
   - Ancak İleri Kinematik (IK) diz ve bilek servo merkez ayarları Pi üzerindeki YAML/JSON kalibrasyon dosyasına yazılır. **`if`** `type == 'imu'`, `eeprom_save` çağrılır. **`else`**, dosya kaydı yapılır.
