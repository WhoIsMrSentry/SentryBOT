# Sub-Agent: calibration-specialist

## Uzmanlık
`None` ve `calibration` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/calibration.md`

## Bileşen haritası
- —

## Dış bağlantılar (neden)
- [[arduino_serial]] (registry): Servo kalibrasyon komutlarını Arduino'ya gönderir.
- [[camera]] (http): `calibration` HTTP ile `camera` modülüne erişir: Kamera stream veya snapshot ister.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `calibration` modülünü import eder (`api`) — Servo kalibrasyon modu.
- [[gateway]] (import): `gateway` kod içinde `calibration` modülünü import eder (`config_loader`) — Servo kalibrasyon modu.
