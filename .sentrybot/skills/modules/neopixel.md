# Skill: neopixel

## Ana bileşen
- Sınıf: `NeoRunner` in `modules/neopixel/xNeopixelService.py`
- Mission: 23 duygu paleti, SPI LED animasyonları

## API özeti
- `GET /animations` → `list_animations()` → —
- `GET /emotions` → `list_emotions()` → —
- `GET /healthz` → `healthz()` → —
- `GET /segments` → `segments()` → —
- `GET /presets` → `presets()` → —
- `POST /preset/apply` → `apply_preset()` → —
- `GET /preset/get` → `get_preset()` → —
- `POST /preset/set` → `set_preset()` → —
- `DELETE /preset/delete` → `delete_preset()` → —
- `POST /clear` → `clear()` → —

## Dış ilişkiler (neden)
- → [[animate]] (http): LED efektleri ile senkronize fiziksel hareket üretir.
- → [[common]] (import): 23 duygu paleti emotion_vocab ile hizalanır.
- → [[logwrapper]] (import): `neopixel` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[diagnostics]] (http): `diagnostics` → `neopixel`: LED animasyon veya duygu preset uygular.
- ← [[gateway]] (http): `gateway` → `neopixel`: LED animasyon veya duygu preset uygular.
- ← [[gateway]] (http): `gateway` → `neopixel`: LED animasyon veya duygu preset uygular.
- ← [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`services`) — 23 duygu paleti, SPI LED animasyonları.
- ← [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`config_loader`) — 23 duygu paleti, SPI LED animasyonları.
- ← [[gateway]] (import): `gateway` kod içinde `neopixel` modülünü import eder (`api`) — 23 duygu paleti, SPI LED animasyonları.
- ← [[interactions]] (registry): Kural motoru CPU/ağ olaylarında LED animasyonu tetikler.
- ← [[logwrapper]] (http): `logwrapper` → `neopixel`: YAML tabanlı servo animasyonu başlatır.
- ← [[notifier]] (http): `notifier` → `neopixel`: LED animasyon veya duygu preset uygular.
- ← [[speak]] (registry): Konuşma sırasında LED canlılık efektleri (liveliness) tetikler.

## Tam bilgi
`.sentrybot/obsidian/modules/neopixel.md` (48 dosya, 11681 satır)
