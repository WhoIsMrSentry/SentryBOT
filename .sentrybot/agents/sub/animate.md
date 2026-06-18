# Sub-Agent: animate-specialist

## Uzmanlık
`xAnimateService` ve `animate` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/animate.md`

## Bileşen haritası
- `xAnimateService` — YAML tabanlı servo animasyon yürütücüsü.

## Dış bağlantılar (neden)
- [[arduino_serial]] (arduino): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[arduino_serial]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[arduino_serial]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[arduino_serial]] (registry): YAML animasyon adımlarını set_pose komutlarına çevirir.

## Gelen bağlantılar (neden)
- [[autonomy]] (http): Duygu durumuna göre vücut animasyonu (stretch, sit, look_around) tetikler.
- [[gateway]] (http): `gateway` → `animate`: YAML tabanlı servo animasyonu başlatır.
- [[gateway]] (import): `gateway` kod içinde `animate` modülünü import eder (`xAnimateService`) — YAML servo animasyon oynatıcı.
- [[gateway]] (import): `gateway` kod içinde `animate` modülünü import eder (`api`) — YAML servo animasyon oynatıcı.
- [[interactions]] (http): Sistem olaylarında veya kural tetiklerinde robot hareketi başlatır.
- [[neopixel]] (http): LED efektleri ile senkronize fiziksel hareket üretir.
- [[neopixel]] (http): LED efektleri ile senkronize fiziksel hareket üretir.
