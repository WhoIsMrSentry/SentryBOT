# Skill: interactions

## Ana bileşen
- Sınıf: `xInteractionsService` in `modules/interactions/xInteractionsService.py`
- Mission: CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme

## API özeti
- `GET /state` → `state()` → —
- `POST /event` → `push_event()` → —
- `POST /effect` → `effect()` → —
- `POST /base` → `base()` → —

## Dış ilişkiler (neden)
- → [[animate]] (http): Sistem olaylarında veya kural tetiklerinde robot hareketi başlatır.
- → [[gateway]] (import): `interactions` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- → [[hardware]] (registry): Sistem metriklerini (CPU, RAM, sıcaklık) okur.
- → [[neopixel]] (registry): Kural motoru CPU/ağ olaylarında LED animasyonu tetikler.
- → [[social_db]] (import): `interactions` içinde `get_default` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).

## Gelen ilişkiler (neden)
- ← [[gateway]] (http): `gateway` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[gateway]] (http): `gateway` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`api`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- ← [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`config_loader`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- ← [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`services`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- ← [[logwrapper]] (http): `logwrapper` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[logwrapper]] (http): `logwrapper` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[scheduler]] (http): `scheduler` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[speech]] (http): `speech` → `interactions`: Sistem olayı veya LED efekti tetikler.
- ← [[vlm_bridge]] (http): `vlm_bridge` → `interactions`: Sistem olayı veya LED efekti tetikler.

## Tam bilgi
`.sentrybot/obsidian/modules/interactions.md` (14 dosya, 1378 satır)
