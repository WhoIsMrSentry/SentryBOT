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
├── tui_app.py                        # Ana Textual Asenkron TUI Uygulaması (SentryBotApp)
├── tui_v2.py                         # CLI başlatıcı (--ascii, --no-color, --no-alt, --no-run)
├── themes.py                         # Lazy Textual Tema Kaydı ve kalıcı tema tercihi
├── sentrybot.tcss                    # Textual CSS Stil Dosyası
├── system_info_tui.py                # Canlı Donanım ve Telemetri Kartı (kaydırmalı TUI)
├── dashboard.py                      # Akıllı terminal log handler (sınırlı/kilitli tekilleştirme)
├── renderer.py                       # ASCII / Unicode uyumlu konsol panel oluşturucu
├── config_loader.py                  # Merkezi DEFAULT_HIDDEN_PATHS ve YAML yükleyici
├── api/router.py                     # /runtime_console/healthz ve korumalı /runtime_console/events
├── services/                         # AsyncGatewayProbe, AsyncRobotManager, AsyncLogStreamer, hardware
├── logwrapper/                       # Merkezi Log Altyapısı (init_logging, run_rotator, handlers, api)
└── widgets/                          # TabMain, TabLogs (Ctrl+S dışa aktarım), TabTelemetry, TabControls, TabConfig, Modal'lar
```

---

## 🖥️ TUI Sekmeleri ve Özellikler

- **01: MAIN (`TabMain`):** CPU/RAM/Disk yükü, servis sağlık kartları, gerçek yeniden başlatma sayacı (`restart_count`), Living Needs göstergesi ve **Autonomy Goal & DecisionTrace Live Feed** kartı. Veri yoksa sahte varsayılanlar yerine `"N/A"` gösterir.
- **02: LOGS (`TabLogs`):** `collections.deque` destekli canlı log akışı, seviye/metin filtresi ve `Ctrl+S` / **Export (Ctrl+S)** düğmesiyle filtrelenmiş logları `logs/exports/` altına dışa aktarma.
- **03: TELEMETRY (`TabTelemetry`):** IMU, ultrasonik engel radarı, pan/tilt/kulak servo çubukları, VU-metre ve DoA radarı.
- **04: CONTROLS (`TabControls`):** `AsyncGatewayProbe` ile tek kalıcı `httpx.AsyncClient` paylaşarak Arduino teleop (`pos`), E-STOP (`/state/set/operational`), `/chat` ve tanılama iş akışlarını çalıştırır.
- **05: CONFIG (`TabConfig`) ve Modallar (`m`, `t`, `i`):** YAML düzenleyici, canlı tema önizleme ve `MemoryExplorerModal` (`SocialDB` + `WorldMemory` sekmeleri ve arka plan SQLite okuma).
- **Kısayollar:** `F1..F5` (Sekmeler), `Ctrl+S` (Log dışa aktar), `Ctrl+L` (Logları temizle), `Ctrl+R`/`Ctrl+K` (Robot restart/stop), `t`/`F6` (Tema), `i`/`F7` (SysInfo), `m`/`F8` (Memory Explorer), `q`/`Ctrl+C` (Çıkış).

---

## 💻 Python Kullanım Örnekleri

### 1. Merkezi Log Sistemini Başlatma (Tüm Modüller İçin Standart)
```python
from modules.common.logger import init_logging
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