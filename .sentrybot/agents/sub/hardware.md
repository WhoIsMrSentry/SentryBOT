# Sub-Agent: hardware-specialist

## Uzmanlık
`None` ve `hardware` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/hardware.md`

## Bileşen haritası
- `AudioService` — Controls TTS output (pyttsx3/piper) and hardware buzzer sounds via ServiceClient.
- `GPIO` — modules/hardware/services/gpio.py
- `LightsService` — Controls NeoPixel LED strips and Laser pointers via ServiceClient HTTP calls.
- `MotorService` — Controls NEMA stepper motors via ServiceClient -> Arduino serial.
- `ServoService` — Interfaces with the Arduino PCA9685 servo system via ServiceClient HTTP calls.
- `SystemSnapshot` — modules/hardware/services/system.py

## Dış bağlantılar (neden)
- [[autonomy]] (import): Sistem yükü verisini otonomi beyinine bildirir.
- [[logwrapper]] (import): `hardware` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `hardware` modülünü import eder (`api`) — CPU/RAM/sıcaklık bilgisi, I2C tarama.
- [[gateway]] (import): `gateway` kod içinde `hardware` modülünü import eder (`config_loader`) — CPU/RAM/sıcaklık bilgisi, I2C tarama.
- [[interactions]] (registry): Sistem metriklerini (CPU, RAM, sıcaklık) okur.
