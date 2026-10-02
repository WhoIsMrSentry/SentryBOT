# SentryBOT V5 — Görsel Çıktı Modülü (`modules/visual_output`)

SentryBOT V5'in duygusal durumunu, canlılık hissini, sistem durumunu ve kullanıcı etkileşimlerini dış dünyaya yansıtan birleşik görsel ifade alt sistemidir. SSD1306 OLED ekran üzerindeki biyolojik göz animasyonlarını ve WS2812B NeoPixel RGB LED şeritlerini yönetir.

---

## 🚀 Hızlı Başlangıç

### 1. Donanım İzinleri ve Paketler

```bash
# Ubuntu / Raspberry Pi OS I2C ve SPI erişim izinleri:
sudo usermod -a -G i2c,spi $USER

# Gerekli Python kütüphaneleri:
pip install Pillow smbus2 spidev fastapi uvicorn pyyaml
# Raspberry Pi donanımında ek olarak:
# pip install rpi_ws281x adafruit-circuitpython-ssd1306
```

---

## 📂 Dizin Yapısı

```
modules/visual_output/
├── architecture_visual_output.dot       # Graphviz Mimari Diyagram Kaynağı
├── architecture_visual_output.svg       # Derlenmiş Vektörel Mimari Şema
├── architecture_visual_output.md        # Kapsamlı Teknik & Sınıf Referansı
├── README.md                            # Bu doküman
├── oled_faces/                          # OLED Yüz İfadeleri ve Göz Animasyonları
│   ├── xOledFacesService.py             # Yüz Koordinatörü & Çizim Servisi
│   ├── services/
│   │   ├── face_coordinator.py         # Temel Ruh Halleri & Oturum Öncelikleri
│   │   ├── face_renderer.py            # SSD1306 Framebuffer & STT Altyazı Barı
│   │   ├── mapper.py                   # Olay -> Ruh Hali Eşleyici
│   │   └── pi_ssd1306_driver.py        # I2C/SPI Düşük Seviye Ekran Sürücüsü
│   └── api/router.py                    # /oled_faces/* FastAPI Yönlendiricisi
└── neopixel/                            # WS2812B RGB LED Şerit ve Halka Aydınlatma
    ├── xNeopixelService.py              # NeoPixel REST Sunucusu (:8092)
    ├── services/
    │   ├── runner.py                    # Asenkron Kare Dağıtıcısı (NeoRunner)
    │   ├── companion_renderer.py        # wake_spin, emotion_pulse Efektleri
    │   ├── segments.py                  # Baş Halkası & Göğüs LED İzolasyonu
    │   └── driver.py                    # Donanımsal SPI / SimStrip Sürücüsü
    └── emotions/palette.py              # Duygu -> RGB Renk Dönüştürücüsü
```

---

## 🛠️ Servisleri Çalıştırma

### 1. NeoPixel Servisini Başlatma (Port: 8092)
```bash
python -m modules.visual_output.neopixel.xNeopixelService
```

### 2. OLED Faces Servisini Başlatma
OLED servisi doğrudan Gateway üzerinden veya bağımsız olarak başlatılabilir:
```bash
python -m modules.visual_output.oled_faces.xOledFacesService
```

---

## 💻 Python Kullanım Örnekleri

### 1. OLED Ekranda Yüz İfadesi Değiştirme ve Altyazı Gösterme
```python
from modules.visual_output.oled_faces.xOledFacesService import xOledFacesService

service = xOledFacesService()
service.start()

# Yüz ifadesini mutlu yap
service.on_interaction_event("emotion.happy", {"duration_s": 4.0})

# Ekranın alt satırında canlı STT transkriptini göster
service.on_interaction_event("speech.final", {"text": "Merhaba! Ben SentryBOT."})
```

### 2. NeoPixel Uyanma Halkası (Wake Spin) ve Duygu Nabzı
```python
from modules.visual_output.neopixel.services.runner import NeoRunner
from modules.visual_output.neopixel.services.driver import NeoDriverConfig

cfg = NeoDriverConfig(num_leds=30, backend="auto")
runner = NeoRunner(cfg, segments=[{"name": "head_ring", "start": 0, "count": 16}])

# Uyandırma kelimesi animasyonu (Dönen turkuaz halka)
runner.companion_set_mode("wake_spin")

# Duygu durumuna uygun renk nabzı (emotion_pulse)
runner.companion_set_mode("emotion_pulse")
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. OLED Yüz İfadesini Değiştirme
```bash
curl -X POST http://127.0.0.1:8080/oled_faces/emotion \
  -H "Content-Type: application/json" \
  -d '{"emotion": "happy", "duration_s": 3.0}'
```

### 2. OLED Ekrana Canlı Altyazı Basma
```bash
curl -X POST http://127.0.0.1:8080/oled_faces/stt_text \
  -H "Content-Type: application/json" \
  -d '{"text": "Devriye görevi başlatılıyor...", "duration_s": 5.0}'
```

### 3. NeoPixel Efektini Başlatma (:8092)
```bash
curl -X POST http://127.0.0.1:8092/neopixel/effect \
  -H "Content-Type: application/json" \
  -d '{"name": "wake_spin", "segment": "head_ring"}'
```

---

## 🧪 Testleri Çalıştırma

Görsel çıktı, OLED yüz koordinatörü ve NeoPixel segment testlerini koşturmak için:

```bash
pytest tests/modules/visual_output -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_visual_output.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/visual_output/architecture_visual_output.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_visual_output.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/visual_output/architecture_visual_output.dot): Graphviz formatında modüler alt sistem çizimi.
- [architecture_visual_output.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/visual_output/architecture_visual_output.svg): Vektörel mimari şeması.
