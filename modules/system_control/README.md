# SentryBOT V5 — Sistem Kontrol Modülü (`modules/system_control`)

SentryBOT V5'in arka plandaki koruyucu denetleme, telemetri, otonom kendini iyileştirme (self-healing), zamanlanmış görevler ve dinamik konfigürasyon altyapısıdır.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install psutil requests fastapi uvicorn pyyaml
```

---

## 📂 Dizin Yapısı

```
modules/system_control/
├── architecture_system_control.dot   # Graphviz Mimari Diyagram Kaynağı
├── architecture_system_control.svg   # Derlenmiş Vektörel Mimari Şema
├── architecture_system_control.md    # Kapsamlı Teknik & Sınıf Referansı
├── README.md                         # Bu doküman
├── diagnostics/                      # Otonom Teşhis & Kendini İyileştirme (Self-Healing)
├── config_center/                    # Dinamik Konfigürasyon & Hassas Veri Maskeleme
├── telemetry/                        # Donanım Telemetrisi (CPU, RAM, Termal Metrikler)
├── scheduler/                        # Periyodik Görev Zamanlayıcısı (Cron & Sweeps)
├── state_manager/                    # Kalıcı Sistem Durumu & Ruh Hali Belleği
└── notifier/                         # Çok Kanallı Bildirim Yöneticisi (Telegram, Discord)
```

---

## 🛡️ Temel Yetenekler

- **Otonom Kendini İyileştirme (Self-Healing):** Çöken alt sistemleri anında tespit eder ve systemd üzerinden yeniden başlatır.
- **Dinamik Konfigürasyon:** Robotu yeniden başlatmadan çalışma zamanında ayar güncelleme desteği.
- **Hassas Veri Maskeleme:** API anahtarlarının ve şifrelerin loglara sızmasını önleyen otomatik maskeleme (`***REDACTED***`).
- **Donanım Telemetrisi:** CPU, RAM ve sıcaklık aşırı limitlere çıktığında koruyucu soğutma modu.

---

## 💻 Python Kullanım Örnekleri

### 1. Sistem Telemetrisini Okuma
```python
from modules.system_control.telemetry.services.host_gauges import HostGauges

gauges = HostGauges()
metrics = gauges.sample()

print(f"CPU Kullanımı: %{metrics.get('cpu_percent')}")
print(f"İşlemci Sıcaklığı: {metrics.get('soc_temp_c')} °C")
```

### 2. Otonom Teşhis (Self-Test) Koşturma
```python
from modules.system_control.diagnostics.services.selftest import SelfTestRunner

runner = SelfTestRunner()
report = runner.run_all()

print("Sistem Sağlık Durumu:", report.get("status"))
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### 1. Sistem Sağlık Testi
```bash
curl -X GET http://127.0.0.1:8080/system/diagnostics/selftest
```

### 2. Donanım Telemetri Değerleri
```bash
curl -X GET http://127.0.0.1:8080/system/telemetry
```

---

## 🧪 Testleri Çalıştırma

Teşhis, kendini iyileştirme, telemetri ve konfigürasyon testlerini koşturmak için:

```bash
pytest tests/modules/system_control -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_system_control.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/system_control/architecture_system_control.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_system_control.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/system_control/architecture_system_control.dot): Graphviz formatında modüler sistem kontrolü çizimi.
- [architecture_system_control.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/system_control/architecture_system_control.svg): Vektörel mimari şeması.
