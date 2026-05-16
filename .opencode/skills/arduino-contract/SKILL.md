---
name: arduino-contract
description: "Arduino kontrat builder ve validator ekler. contract.py'ye build_* ve validate_* fonksiyonları, zorunlu testler."
---

# Arduino Contract

Arduino komut kontratı ekleme prosedürü.

## Zorunlu Çıktılar (Aynı PR'da)
1. `modules/arduino_serial/contract.py`'ye `build_<cmd>` fonksiyonu
2. `modules/arduino_serial/contract.py`'ye `validate_<cmd>` fonksiyonu
3. Validator unit testi
4. Gateway davranış testi

## Kurallar
- Elle `{"cmd": ...}` payload yazmak YASAK
- Kritik komutlar `/arduino/request` kullanır (ACK bekler)
- Timeout: 0.8–1.5s arası

## Tam Prosedür
`.sentrybot/skills/arduino-contract.md` dosyasını oku.
