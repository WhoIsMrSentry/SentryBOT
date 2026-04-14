# Arduino Serial Modülü Mimarisi

Arduino Serial modülü (`modules/arduino_serial`), Raspberry Pi/Jetson ile Arduino Mega arasındaki düşük seviyeli iletişimi NDJSON (Newline Delimited JSON) protokolü üzerinden yönetir.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Aşağıdaki diyagram, seri portun nasıl başlatıldığını, arka plandaki okuma döngüsünü, ve gelen/giden JSON mesajlarının nasıl filtrelendiğini (if/else) gösterir:

```mermaid
flowchart TD
    %% Başlatma Mantığı
    START([start]) --> CHK_THREAD{"Okuma Thread'i <br> çalışıyor mu?"}
    CHK_THREAD -- Evet --> IGNORE([Hiçbir Şey Yapma])
    CHK_THREAD -- Hayır --> FIND_PORT(Seri Portu Bul <br> _autodetect_port)
    
    FIND_PORT --> CHK_PORT{"Port Bulundu mu?"}
    CHK_PORT -- Hayır --> ERR_START([HATA: Port Yok veya Erişilemez])
    CHK_PORT -- Evet --> OPEN_SERIAL(SerialTransport Başlat)
    
    OPEN_SERIAL --> CREATE_THREADS(Send ve Read <br> Queue Oluştur)
    CREATE_THREADS --> RUN_THREAD[Arka Plan _read_loop Oku]

    %% Arka Plan Okuma Döngüsü (Read Loop)
    subgraph ReadLoop [Arka Plan Okuma Akışı]
        direction TB
        LOOP_START((Döngü Başı)) --> READ_LINE{"Seri Porttan<br>Satır Oku"}
        READ_LINE -- Boş / Timeout --> LOOP_START
        READ_LINE -- Veri Var --> PARSE_JSON{"JSON Parse <br> Başarılı mı?"}
        PARSE_JSON -- Hayır --> LOG_ERR[Hata Logla] --> LOOP_START
        PARSE_JSON -- Evet --> INGEST(JSON Verisini İşle <br> _ingest_message)

        INGEST --> CHK_TYPE{Gelen Mesaj Türü}
        
        CHK_TYPE -- RFID Olayı --> EVENT_RFID[RFID Handler <br> _record_rfid / Webhook] --> LOOP_START
        CHK_TYPE -- Telemetri --> EVENT_TLM[Telemetri Handler <br> Global Durum] --> LOOP_START
        CHK_TYPE -- Yanıt (ok / error) --> QUEUE_PUSH[Uygulama Yanıt<br>Kuyruğuna Koy] --> LOOP_START
    end
    
    RUN_THREAD --> LOOP_START

    %% Komut Gönderme Akışı
    subgraph WriteCycle [Komut Gönderme - send/request]
        direction TB
        API_CALL([request_cmd]) --> MAKE_JSON(JSON'a Çevir + <br> Satır Sonu Ekle)
        MAKE_JSON --> CHK_ALIVE{"Bağlantı Açık mı?"}
        CHK_ALIVE -- Hayır --> RET_NONE([None Döndür])
        CHK_ALIVE -- Evet --> WRITE(Serial Write)
        WRITE --> WAIT_Q{"Okuma Kuyruğunda<br>Yanıt Bekle - Timeout"}
        WAIT_Q -- Timeout --> RET_ERR([Hata Formatı Döndür])
        WAIT_Q -- Yanıt Geldi --> RET_RESP([Yanıtı Döndür])
    end
```

## 🔄 İlişkisel Etkileşimler

```mermaid
erDiagram
    ArduinoSerialService ||--|| SerialTransport : uses
    ArduinoSerialService ||--o{ HttpCaller : provides

    SerialTransport {
        string port
        int baudrate
    }
    ArduinoSerialService {
        string last_rfid
        bool reader_active
    }
    HttpCaller {
        string request_source
        string json_command
    }
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **`_autodetect_port(fallback_port)`**
   - **`if`** fallback `AUTO` ise: PySerial `list_ports` ile mevcut cihazları tara.
     - **İç `for` döngüsü**: `/dev/ttyUSB`, `/dev/ttyACM` önekli portları (RPi/Linux), veya `COM` önekli portları (Windows) bul. Bulursa ilkini kullan.
   - **`else`**: Belirtilen spesifik portu kullan.
   - Eğer port bulunamazsa veya cihaz hatalıysa sisteme uyarı ver (`logger.error`).
2. **`request(obj, timeout)` (Senkron Çağrı Mantığı)**
   - Arduino'ya istek gönderilir.
   - Öncesinde yanıt kuyruğu temizlenir (Eski okunmamış çöpleri temizlemek için `Empty` exception alana kadar döngü çalışır).
   - **`while`**: `timeout` süresince `_lines` kuyruğunu bekle.
     - **`if`** doğru formatta cevap gelirse dön, yoksa döngüde beklemeye devam et.
     - Zaman aşımı olursa (Arduino yanıt vermedi), otomatik `{"error": "timeout"}` simüle edip döndür.
3. **RFID Yetkilendirmesi (`authorize_rfid`)**
   - **`if`** `uid` parametresi verilmişse: Normalizasyon yapılır (`F3-A1...` -> `F3A1...`), kuyruklar temizlenir ve UID özel bir değişkende 5 saniye boyunca (window) tutulur, bu sürede gelen aynı UID okumaları gözden kaçmaması içindir.
