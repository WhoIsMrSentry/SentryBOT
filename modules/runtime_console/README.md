# SentryBOT V5 — Runtime Console Modülü (`modules/runtime_console`)

SentryBOT V5'in interaktif terminal arayüzü (Textual TUI) ve 14 modülün tamamı tarafından kullanılan merkezi günlükleme (`logwrapper`) altyapısıdır.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

```bash
# Gerekli Python kütüphaneleri:
pip install textual rich psutil pyyaml requests
```

### 2. Konsol Arayüzünü Başlatma

```bash
# Zengin TUI konsolunu başlatma:
python -m modules.runtime_console.tui_app
```

---

## 📂 Dizin Yapısı

```
modules/runtime_console/
├── tui_app.py                        # Ana Textual Asenkron TUI Uygulaması
├── themes.py                         # Renk Temaları (Dark, Cyberpunk, Monokai)
├── sentrybot.tcss                    # Textual CSS Stil Dosyası
├── system_info_tui.py                # Canlı Donanım ve Telemetri Kartı
├── architecture_runtime_console.dot  # Graphviz Mimari Diyagram Kaynağı
├── architecture_runtime_console.svg  # Derlenmiş Vektörel Mimari Şema
├── architecture_runtime_console.md   # Kapsamlı Teknik & Sınıf Referansı
├── README.md                         # Bu doküman
├── logwrapper/                       # Merkezi Log Altyapısı
│   ├── __init__.py                   # init_logging() Singleton
│   ├── separate_file_routing.py      # Seviye Bazlı Dosya Ayrıştırıcı (warnings, errors)
│   └── run_rotator.py                # Oturum Loglarını Arşivleme & Temizleme
└── widgets/                          # TUI Sekme Bileşenleri ve Kartlar
```

---

## 🖥️ TUI Sekmeleri ve Özellikler

- **Ana Sekme (Tab Main):** Canlı log akışı, servis sağlık durumu ve süreç butonları.
- **Telemetri (Tab Telemetry):** CPU, RAM ve sıcaklık geçmişi grafikleri.
- **Konfigürasyon (Tab Config):** YAML ağacı ve dinamik ayar görüntüleyici.
- **Kısayollar:** `q` (Çıkış), `t` (Tema değiştir), `c` (Logları temizle), `1..3` (Sekme geçişi).

---

## 💻 Python Kullanım Örnekleri

### 1. Merkezi Log Sistemini Başlatma (Tüm Modüller İçin Standart)
```python
from modules.runtime_console.logwrapper import init_logging
import logging

# Log altyapısını başlat ve önceki oturumu arşivle
init_logging(level=logging.INFO)

logger = logging.getLogger("my_module")
logger.info("Modül başarıyla başlatıldı.")
logger.warning("Dikkat: Hafif sıcaklık artışı tespit edildi.")
```

---

## 🧪 Testleri Çalıştırma

Logwrapper, ayrı dosya yönlendirmesi, TUI derleme ve tema testlerini koşturmak için:

```bash
pytest tests/modules/runtime_console -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_runtime_console.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/runtime_console/architecture_runtime_console.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_runtime_console.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/runtime_console/architecture_runtime_console.dot): Graphviz formatında modüler konsol çizimi.
- [architecture_runtime_console.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/runtime_console/architecture_runtime_console.svg): Vektörel mimari şeması.