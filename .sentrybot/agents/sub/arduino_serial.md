# Sub-Agent: arduino_serial-specialist

## Uzmanlık
`SerialTransport` ve `arduino_serial` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/arduino_serial.md`

## Bileşen haritası
- `ArduinoDriver` — High-level convenience layer over xArduinoSerialService.
- `SerialTransport` — Thin wrapper around pyserial for dependency injection in tests.

## Dış bağlantılar (neden)
- [[config_center]] (import): `arduino_serial` → `config_center`: config/agent.yaml dosyasından ayar okur.

## Gelen bağlantılar (neden)
- [[animate]] (arduino): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[animate]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[animate]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[animate]] (registry): YAML animasyon adımlarını set_pose komutlarına çevirir.
- [[autonomy]] (arduino): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[autonomy]] (import): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[autonomy]] (registry): Karar sonrası servo/hareket komutlarını donanıma iletir.
- [[calibration]] (registry): Servo kalibrasyon komutlarını Arduino'ya gönderir.
- [[diagnostics]] (http): Arduino bağlantı sağlık testi yapar.
- [[diagnostics]] (registry): Arduino bağlantı sağlık testi yapar.
- [[gateway]] (arduino): Tüm /arduino/* isteklerini serial modüle proxy eder.
- [[gateway]] (http): Tüm /arduino/* isteklerini serial modüle proxy eder.
