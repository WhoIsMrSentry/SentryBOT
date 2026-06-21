# Sub-Agent: piservo-specialist

## Uzmanlık
`None` ve `piservo` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/piservo.md`

## Bileşen haritası
- `Servo` — modules/piservo/services/driver.py
- `ServoConfig` — modules/piservo/services/driver.py
- `_ArduinoWrapper` — modules/piservo/services/driver.py
- `_PigpioWrapper` — modules/piservo/services/driver.py
- `_SimGPIO` — modules/piservo/services/driver.py
- `EarPose` — modules/piservo/services/ears.py
- `EarRunner` — modules/piservo/services/runner.py

## Dış bağlantılar (neden)
- [[arduino_serial]] (arduino): Kulak servo komutları için seri haberleşme (bazı kurulumlarda).
- [[arduino_serial]] (import): Kulak servo komutları için seri haberleşme (bazı kurulumlarda).
- [[common]] (import): Kulak pozisyonları duygu sözlüğü ile eşlenir.
- [[logwrapper]] (import): `piservo` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`config_loader`) — Raspberry Pi GPIO PWM kulak servoları.
- [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`api`) — Raspberry Pi GPIO PWM kulak servoları.
- [[gateway]] (import): `gateway` kod içinde `piservo` modülünü import eder (`services`) — Raspberry Pi GPIO PWM kulak servoları.
