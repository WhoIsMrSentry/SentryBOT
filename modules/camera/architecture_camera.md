# Camera Modülü Mimarisi

Camera modülü (`modules/camera`), cihaza bağlı olan kameradan (veya V4L2 cihazından) sürekli görüntü akışını sağlayan ve bunu MJPEG formatında API üzerinden ağa / diğer modüllere sunan donanım bağdaştırıcısıdır.

## 🏗️ İş Akışı ve Karar Mekanizmaları (Flowchart)

Kamera thread'inin nasıl çalıştığını, çökme anında donanımı nasıl resetlediğini (`retry`) ve web üzerinden nasıl görüntülendiğini (MJPEG Streaming) gösteren mantık:

```mermaid
flowchart TD
    %% Ana Thread
    START_THREAD([Kamera Capture Thread]) --> HW_INIT(Donanıma Bağlan: /dev/video0)
    
    HW_INIT --> CHK_HW{"Kamera Cihazı<br>Açıldı mı?"}
    
    CHK_HW -- Hayır --> LOG_ERR[Hata: Kamera Bulunamadı] --> RETRY_WAIT(Saniye Bekle, Tekrar Dene) --> HW_INIT
    CHK_HW -- Evet --> ENTER_LOOP[Okuma Döngüsüne Gir]
    
    %% Çerçeve / Frame Okuma Döngüsü
    subgraph Capture Loop [Sürekli Okuma Döngüsü]
        direction TB
        ENTER_LOOP --> GRAB_FRAME(Kareyi Kapat - read)
        
        GRAB_FRAME --> CHK_FRAME{"Kare Başarılı <br> Geldi mi?"}
        CHK_FRAME -- Hayır --> LOG_DROP[Uyarı: Frame Dropped] --> RECONN_HW(Cihazı Kapat / Yeniden Aç) --> ENTER_LOOP
        
        CHK_FRAME -- Evet --> FPS_THROTTLE{"Hedef FPS<br>Geçildi mi?"}
        FPS_THROTTLE -- Evet --> SKIP((Kareyi Atla)) --> GRAB_FRAME
        
        FPS_THROTTLE -- Hayır --> ENCODE_JPEG(JPEG Olarak Sıkıştır)
    end
    
    %% Frame Publishing
    subgraph Publisher API [Yayın Mekanizması]
        direction TB
        ENCODE_JPEG --> LOCK_VAR[MUTEX Kilidi Al]
        LOCK_VAR --> UPDATE_VAR{"global_frame değişkenini<br>güncelle"}
        UPDATE_VAR --> UNLOCK_VAR[MUTEX'i Bırak]
        UNLOCK_VAR --> SIGNAL_EVENT(Tüm bekleyen web<br>istemcilerine Event Yolla)
    end
    
    SIGNAL_EVENT --> GRAB_FRAME
    
    %% Web Stream İstemcileri
    API_REQ([GET /camera/stream]) --> WEB_LOOP[Sonsuz Yield Döngüsü]
    WEB_LOOP --> WAIT_EVT(Signal Bekle)
    WAIT_EVT --> READ_F(global_frame'i oku)
    READ_F --> SEND_F(HTTP Multi-part olarak Yolla) --> WEB_LOOP
```

## 🔄 İlişkisel Etkileşimler (Veri Akışı)

```mermaid
erDiagram
    CameraCapture ||--o{"WebClients : streams_to
    VisionBridge ||--|| CameraCapture : polls_latest_frame
    
    CameraCapture {
        bytes current_frame 'Son başarılı JPEG'
                threading.Event frame_ready
                start
                stop"}
    
    VisionBridge {fetch_frame_for_yolo}
```

## ⚙️ Detaylı Karar Mantığı (if/else)

1. **Donanım Çökmesini İyileştirme (Auto-Recovery)**
   - Kameralar fiziksel kablo veya yoğun akım sebebiyle anlık kopmalar yaşayabilir.
   - **`while` loop içinde `if not ret`**: Eğer `cv2.VideoCapture` `False` sonuç döndürürse yazılım çökmez. Hemen `cap.release()` yaparak kamera buffer'ını boşaltır, 2 saniye `time.sleep()` atar ve tekrar (`cap = cv2.VideoCapture(0)`) başlatmayı dener. Bu sistemin "robot devrilse bile" kurtarılabilir olmasını sağlar.
2. **Yayın Modeli (Publisher - Subscriber)**
   - API'ye (örneğin Web tarayıcısı `/camera/stream` adresine girdiğinde) bağlanmış birden fazla kullanıcı veya modül olabilir.
   - Her istek için ayrı ayrı kameradan okuma YAPILMAZ (USB veriyolunu kitler).
   - Bunun yerine tek bir ana thread, kamerayı okur ve bellekteki (RAM) `global_frame` adlı bayte array'ini (**`if`** `mutex.acquire()` kilitleri içinde) ezerek günceller.
    - Okumak isteyen herkes sadece RAM'den okur, böylece RPi 10 cihaza birden yayın yapabilir (CPU tabanlı MJPEG multicast). Görüntü işleme (VLM Bridge) de bu RAM adresindeki son resmi çeker.
