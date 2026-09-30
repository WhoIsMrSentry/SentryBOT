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
from modules.camera.xCameraService import xCameraService

camera_svc = xCameraService()
camera_svc.start()

# En güncel JPEG karesini bayt olarak alma
jpeg_bytes = camera_svc.get_frame(as_jpeg=True)
if jpeg_bytes:
    with open("snapshot.jpg", "wb") as f:
        f.write(jpeg_bytes)
```

### 2. HTTP Üzerinden Kare Çekme (cURL)
```bash
curl -o snapshot.jpg http://127.0.0.1:8080/camera/frame
```

---

## 📡 REST API Endpointleri

| Metot | Endpoint | Açıklama |
|---|---|---|
| `GET` | `/camera/healthz` | Kamera servis ve donanım sağlık kontrolü |
| `GET` | `/camera/frame` | Son yakalanan tekil JPEG görüntüsü |
| `GET` | `/camera/status` | Aktif backend, gerçek FPS ve çözünürlük bilgisi |
| `GET` | `/camera/imx500/status` | IMX500 on-sensor AI hızlandırıcısının durumu |

---

## 🧪 Testlerin Çalıştırılması

```bash
pytest tests/modules/camera -v
```