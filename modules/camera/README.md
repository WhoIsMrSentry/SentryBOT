# Camera — Görüntü Yakalama ve Donanım Servisi

`modules.camera`, SentryBOT platformunun fiziksel optik girdi katmanıdır. USB web kameralarını, Raspberry Pi Camera (CSI) donanımını ve Raspberry Pi AI Camera (Sony IMX500 on-sensor NPU) modüllerini yönetir.

Mimari detaylar, sınıf yapıları ve veri akış diyagramları için:
- 📖 [architecture_camera.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/camera/architecture_camera.md)
- 📊 [architecture_camera.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/camera/architecture_camera.dot) (Graphviz DOT kaynağı)
- 🖼️ [architecture_camera.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/camera/architecture_camera.svg)

---

## 🚀 Temel Yetenekler

1. **Çoklu Donanım Desteği:** V4L2 USB kameralar, libcamera / Picamera2 ve Raspberry Pi 5 tam uyumluluğu.
2. **On-Sensor AI (Sony IMX500):** Raspberry Pi AI Camera üzerindeki yerleşik NPU ile sıfır host-CPU yüküyle nesne ve insan algılama.
3. **Süreç Koruması (`DeviceLock`):** Kamera aygıtının çakışmasını ve kilitlenmesini engelleyen dosya kilidi yönetimi.
4. **Yüksek Performanslı Tamponlama:** Bağımsız arka plan iş parçacığıyla sürekli kare yakalama ve en son karenin thread-safe JPEG tamponunda saklanması.
5. **Görsel Hedef Takibi (`TrackingService`):** Algılanan hedefin merkez sapmasını hesaplayıp pan/tilt kafasına açı düzeltmesi üretme.

---

## 🛠️ Hızlı Kullanım Örnekleri

### 1. Servisi Başlatma ve Son Kareyi Alma (Python)
```python
from modules.camera.services.capture import CameraCapture, CaptureConfig, FramePublisher

pub = FramePublisher()
cap = CameraCapture(CaptureConfig(backend="picamera2"), pub)
cap.start()

# Yalnızca ihtiyaç duyulduğunda tembel JPEG kodlaması üretir
jpeg_bytes = pub.get_jpeg()
if jpeg_bytes:
    with open("snapshot.jpg", "wb") as f:
        f.write(jpeg_bytes)
```

### 2. HTTP Üzerinden Kare Çekme (cURL)
```bash
curl -o snapshot.jpg http://127.0.0.1:8000/camera/snap
```

---

## 📡 REST API Endpointleri

| Metot | Endpoint | Açıklama |
|---|---|---|
| `GET` | `/camera/healthz` | Kamera servis ve donanım sağlık kontrolü |
| `GET` | `/camera/snap` | Son yakalanan tekil JPEG karesi (tembel kodlama) |
| `GET` | `/camera/video` | MJPEG akışı (`FramePublisher` abone sayacı ve `Condition` ile) |
| `GET` | `/camera/status` | Aktif backend, çözünürlük, FPS, abone sayısı ve IMX500 durumu |
| `GET` | `/camera/onsensor/latest` | Son IMX500 on-sensor tespit özeti |
| `GET/POST` | `/camera/tracking/tracks`, `/target`, `/select` | IMX500 hedef takibi ve seçimi |
| `POST` | `/camera/start`, `/camera/stop` | Kilit korumalı akış başlatma/durdurma |

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/camera -v
```