# Vendor — Harici Kaynaklar

## esp-bridge-mcp-robot (Pip göz motoru)

**Upstream:** [WhoIsMrSentry/esp-bridge-mcp-robot](https://github.com/WhoIsMrSentry/esp-bridge-mcp-robot)

SentryBOT'ta Pip tarzı prosedürel OLED göz motoru `modules/oled_faces/services/eyes/` içinde çalışır.
Upstream kaynak referansı: `vendor/esp-bridge-mcp-robot/src/modules/espbridge/eyes/`

### Güncelleme

```bash
# İlk kurulum
git clone --depth 1 https://github.com/WhoIsMrSentry/esp-bridge-mcp-robot.git vendor/esp-bridge-mcp-robot

# Güncelleme
cd vendor/esp-bridge-mcp-robot && git pull origin main && cd ../..

# Katalog karşılaştırması (SentryBOT vs upstream)
python3 tools/sync_pip_eyes_catalog.py
```

### SentryBOT vs Pip farkı

| Alan | Pip (upstream) | SentryBOT |
|------|----------------|-----------|
| Donanım | ESP32 BLE + OLED | Pi I2C SSD1306 (`oled_faces`) |
| Göz motoru | `espbridge/eyes/` | `modules/oled_faces/services/eyes/` |
| Ekstra mood | — | `smoking` (robot özel) |
| Ekstra gesture | `smoke`, `nod`, `laugh` … | sadece bakış/blink |
| activities | 15 (upstream tam set) | robot idle + dev seti |
| LED / servo | yok | `neopixel`, `animate`, `piservo` ile senkron |

Birleşik ifade haritası: [`docs/robot_expression_map.md`](../docs/robot_expression_map.md)
