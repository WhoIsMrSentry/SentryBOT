# Sub-Agent: neopixel-specialist

## Uzmanlık
`NeoRunner` ve `neopixel` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/neopixel.md`

## Bileşen haritası
- `NeoDriver` — modules/neopixel/services/driver.py
- `NeoDriverConfig` — modules/neopixel/services/driver.py
- `_ArduinoStrip` — Arduino backend support removed in favor of Pi native driver.
- `_SimStrip` — Simple simulator for development environments without hardware.
- `_StripProto` — modules/neopixel/services/driver.py
- `NeoRunner` — modules/neopixel/services/runner.py
- `_SegmentView` — Adapter that exposes a driver sub-range as if it were a full strip.

## Dış bağlantılar (neden)
- [[animate]] (http): LED efektleri ile senkronize fiziksel hareket üretir.
- [[common]] (import): 23 duygu paleti emotion_vocab ile hizalanır.
- [[logwrapper]] (import): `neopixel` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[diagnostics]] (http): `diagnostics` → `neopixel`: LED animasyon veya duygu preset uygular.
- [[gateway]] (http): `gateway` → `neopixel`: LED animasyon veya duygu preset uygular.
- [[gateway]] (http): `gateway` → `neopixel`: LED animasyon veya duygu preset uygular.
- [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`services`) — 23 duygu paleti, SPI LED animasyonları.
- [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`config_loader`) — 23 duygu paleti, SPI LED animasyonları.
- [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`api`) — 23 duygu paleti, SPI LED animasyonları.
- [[interactions]] (registry): Kural motoru CPU/ağ olaylarında LED animasyonu tetikler.
- [[logwrapper]] (http): `logwrapper` → `neopixel`: YAML tabanlı servo animasyonu başlatır.
- [[notifier]] (http): `notifier` → `neopixel`: LED animasyon veya duygu preset uygular.
- [[speak]] (registry): Konuşma sırasında LED canlılık efektleri (liveliness) tetikler.
