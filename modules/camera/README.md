# Camera Module

SentryBOT'un ana görüntü yakalama ve yayın servisidir. `PiCamera2` (veya OpenCV/USB kamera fallback) kullanarak sürekli kare yakalar, MJPEG yayınlar ve IMX500 donanımsal yapay zeka hızlandırıcısına kare gönderimi yapar.

## Özellikler
- **Gerçek Zamanlı Görüntü (MJPEG):** Tarayıcı veya diğer servisler için HTTP üzerinden sürekli MJPEG video yayını sağlar.
- **Anlık Görüntü (Snapshot):** Tek kare (JPEG) fotoğraf yakalama uç noktası.
- **OnSensor / IMX500 Desteği:** Donanımsal yapay zeka kameraları (IMX500 gibi) üzerinden elde edilen takip (tracking) ve kutu algılama verilerini API olarak sunar.

## API Uç Noktaları

Tüm uç noktalar varsayılan olarak `/camera` prefix'i altındadır.

### Görüntü Sağlayıcı (Stream)
- `GET /camera/video`
  Canlı MJPEG video akışını döndürür (`multipart/x-mixed-replace`).
- `GET /camera/snap`
  Anlık (tek kare) JPEG formatında fotoğraf döner.

### Durum ve Yönetim
- `GET /camera/healthz`
  Kamera ve IMX500 donanımının genel sağlık durumunu döner.
- `GET /camera/status`
  Kamera yakalama (capture), IMX500 ve OnSensor veriyolu durumunun daha kapsamlı bir özetini sunar.
- `POST /camera/start`
  Kamera donanımını başlatır (ve IMX500 koşucusunu capture'a bağlar).
- `POST /camera/stop`
  Kamera donanımını kapatır/durdurur.

### Yapay Zeka / Takip (Tracking)
- `GET /camera/onsensor/latest`
  IMX500 üzerinden gelen en son nesne algılama veya sınıflandırma verisini (JSON) döner.
- `GET /camera/tracking/tracks`
  Kameranın takip etmekte olduğu aktif algılama kutularının/izlerinin (track list) detaylarını döner.
- `GET /camera/tracking/target`
  Mevcut seçilmiş/kilitlenilmiş hedefi döner.
- `POST /camera/tracking/select`
  Takip edilecek nesne için kilitlenme stratejisini belirler.
  **Gövde (JSON):**
  - `label` (str): Takip edilecek sınıf (ör. "person").
  - `strategy` (str): "largest" (en büyük), "center" (merkeze en yakın) veya "confidence".
  - `track_id` (int, opsiyonel): Belirli bir track id'sine doğrudan kilitlenir.

## Konfigürasyon

Modülün ayarları (`config/config.yml`):
- `enabled`: Kameranın varsayılan olarak etkin olup olmayacağı.
- Çözünürlük, `fps` ve aygıt yolları.
- Varsa IMX500 konfigürasyon seçenekleri.
