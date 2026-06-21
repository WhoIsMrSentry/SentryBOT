# Sub-Agent: interactions-specialist

## Uzmanlık
`xInteractionsService` ve `interactions` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/interactions.md`

## Bileşen haritası
- `NeoHttpClient` — modules/interactions/services/adapters/neopixel_client.py
- `NoOpNeoClient` — modules/interactions/services/adapters/neopixel_client.py
- `InteractionEngine` — modules/interactions/services/engine.py
- `_LocalNeoAdapter` — modules/interactions/services/engine.py
- `MetricsCollector` — modules/interactions/services/metrics.py
- `SysMetrics` — modules/interactions/services/metrics.py
- `Rule` — modules/interactions/services/rules.py
- `xInteractionsService` — modules/interactions/xInteractionsService.py

## Dış bağlantılar (neden)
- [[animate]] (http): Sistem olaylarında veya kural tetiklerinde robot hareketi başlatır.
- [[gateway]] (import): `interactions` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- [[hardware]] (registry): Sistem metriklerini (CPU, RAM, sıcaklık) okur.
- [[neopixel]] (registry): Kural motoru CPU/ağ olaylarında LED animasyonu tetikler.
- [[social_db]] (import): `interactions` içinde `get_default` import edilir; `social_db` modülünün yeteneğini kullanır (SQLite kişi hafızası, ilişki/tanıma seviyeleri).

## Gelen bağlantılar (neden)
- [[gateway]] (http): `gateway` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[gateway]] (http): `gateway` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`api`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`config_loader`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- [[gateway]] (import): `gateway` kod içinde `interactions` modülünü import eder (`services`) — CPU/ağ metrikleri, kural motoru, NeoPixel tetikleme.
- [[logwrapper]] (http): `logwrapper` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[logwrapper]] (http): `logwrapper` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[scheduler]] (http): `scheduler` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[speech]] (http): `speech` → `interactions`: Sistem olayı veya LED efekti tetikler.
- [[vlm_bridge]] (http): `vlm_bridge` → `interactions`: Sistem olayı veya LED efekti tetikler.
