# Skill: hardware

## Ana bileşen
- Sınıf: `None` in `modules/hardware/xHardwareService.py`
- Mission: CPU/RAM/sıcaklık bilgisi, I2C tarama

## API özeti
- `GET /healthz` → `healthz()` → —
- `GET /system` → `system()` → —
- `GET /i2c/scan` → `i2c_scan_endpoint()` → —
- `GET /gpio/info` → `gpio_info()` → —

## Dış ilişkiler (neden)
- → [[autonomy]] (import): Sistem yükü verisini otonomi beyinine bildirir.
- → [[logwrapper]] (import): `hardware` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.

## Gelen ilişkiler (neden)
- ← [[gateway]] (import): `gateway` kod içinde `hardware` modülünü import eder (`api`) — CPU/RAM/sıcaklık bilgisi, I2C tarama.
- ← [[gateway]] (import): `gateway` kod içinde `hardware` modülünü import eder (`config_loader`) — CPU/RAM/sıcaklık bilgisi, I2C tarama.
- ← [[interactions]] (registry): Sistem metriklerini (CPU, RAM, sıcaklık) okur.

## Tam bilgi
`.sentrybot/obsidian/modules/hardware.md` (17 dosya, 522 satır)
