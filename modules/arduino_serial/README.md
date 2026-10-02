# SentryBOT V5 — Arduino Seri Haberleşme Modülü (`modules/arduino_serial`)

SentryBOT V5'in yüksek seviyeli bilişsel süreçleri ile alt seviye mikrodenetleyicileri (Arduino Mega & ESP32) arasındaki donanım soyutlama katmanıdır (HAL). Servo motorların, diferansiyel sürüş adım motorlarının, RC522 RFID okuyucunun ve piezo buzzer seslerinin yönetimini üstlenir.

> [!IMPORTANT]
> **KRİTİK KONTRAKT KURALI:**
> Sistemde elle JSON/sözlük payload üretmek (`{"cmd": "set_servo", ...}`) kesinlikle YASAKTIR. Tüm komutlar `contract.py` içerisindeki `CommandBuilder` fonksiyonları kullanılarak üretilmeli ve doğrulanmalıdır.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Ubuntu / Raspberry Pi OS için seri port erişim izinleri:
sudo usermod -a -G dialout $USER

# Gerekli Python kütüphaneleri:
pip install pyserial requests fastapi uvicorn pyyaml
```

---

## 📂 Dizin Yapısı

```
modules/arduino_serial/
├── xArduinoSerialService.py              # Merkezi HAL Servisi ve Olay Döngüleri
├── contract.py                           # Standart Komut Üreticileri (CommandBuilder)
├── contract_validators.py                # Fiziksel Açı/Hız Sınırları ve Doğrulayıcılar
├── command_validators.py                 # Giden Komut Şema Doğrulayıcısı
├── config_loader.py                      # YAML Yapılandırma Yükleyici
├── head_arbiter_integration.py           # HeadControlArbiter Kafa Hakemi Entegrasyonu
├── architecture_arduino_serial.dot       # Graphviz Mimari Diyagram Kaynağı
├── architecture_arduino_serial.svg       # Derlenmiş Vektörel Mimari Şema
├── architecture_arduino_serial.md        # Kapsamlı Teknik & Sınıf Referansı
├── README.md                             # Bu doküman
├── api/
│   └── router.py                         # FastAPI Uç Noktaları (:8091 - /arduino/*)
├── transports/                           # Taşıma Katmanı
│   ├── serial_transport.py               # PySerial Doğrudan USB/UART Bağlantısı
│   ├── esp_transport.py                  # ESP32 WiFi / HTTP Köprü İstemcisi
│   └── firmware_helpers.py               # Donanım El Sıkışma & Versiyon Kontrolü
└── services/                             # Yardımcı Donanım Servisleri
    ├── port_detector.py                  # Linux / Windows Otomatik Port Tespiti
    ├── rfid_handler.py                   # RC522 RFID Etiket Okuma & Debounce (2.0s)
    ├── cute_catalog.py                   # Duygusal Buzzer Melodileri Kataloğu
    └── serial_loops.py                   # Dedicated RX Thread & Queue (max: 100)
```

---

## 🛠️ Servisi Çalıştırma

### Bağımsız API Sunucusu Olarak Başlatma
```bash
python -m modules.arduino_serial.xArduinoSerialService
# Varsayılan: 0.0.0.0:8091 adresinde FastAPI sunucusunu açar.
```

---

## 💻 Python Kullanım Örnekleri

### 1. Standart Komut Üretici (`contract.py`) ile Servo Kontrolü
```python
from modules.arduino_serial.contract import build_set_servo_cmd, SERVO_INDEX_PAN
from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService

service = xArduinoSerialService()
service.start()

# Baş servosu için güvenli açı komutu üret (Elle sözlük yazılmaz!)
cmd = build_set_servo_cmd(index=SERVO_INDEX_PAN, deg=90.0)

# Donanıma güvenle gönder
success = service.send(cmd)
print("Komut iletildi mi:", success)
```

### 2. Baş Canlılığı (Liveliness) ve Sevimli Buzzer Sesi
```python
from modules.arduino_serial.contract import build_liveliness_cmd, build_cute_cmd

# Otonom nefes alma hareketi başlat
liveliness_cmd = build_liveliness_cmd(mode="breathing", enabled=True, amplitude_deg=6.0)
service.send(liveliness_cmd)

# Duygusal onay sesi çal
cute_cmd = build_cute_cmd(name="happy")
service.send(cute_cmd)
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Servo Pozisyonu Ayarlama
```bash
curl -X POST http://127.0.0.1:8091/arduino/servo \
  -H "Content-Type: application/json" \
  -d '{"index": 0, "deg": 85.0}'
```

### 2. Diferansiyel Sürüş
```bash
curl -X POST http://127.0.0.1:8091/arduino/drive \
  -H "Content-Type: application/json" \
  -d '{"vx": 0.2, "vtheta": 0.0, "duration_ms": 1000}'
```

### 3. Donanım Bağlantı Durumu (Status)
```bash
curl -X GET http://127.0.0.1:8091/arduino/status
```

---

## 🧪 Testleri Çalıştırma

Donanım soyutlama, port algılama ve kontrat doğrulayıcı testlerini koşturmak için:

```bash
pytest tests/modules/arduino_serial -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_arduino_serial.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/arduino_serial/architecture_arduino_serial.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_arduino_serial.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/arduino_serial/architecture_arduino_serial.dot): Graphviz formatında modüler alt sistem çizimi.
- [architecture_arduino_serial.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/arduino_serial/architecture_arduino_serial.svg): Vektörel mimari şeması.