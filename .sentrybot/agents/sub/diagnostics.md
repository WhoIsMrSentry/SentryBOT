# Sub-Agent: diagnostics-specialist

## Uzmanlık
`None` ve `diagnostics` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/diagnostics.md`

## Bileşen haritası
- —

## Dış bağlantılar (neden)
- [[arduino_serial]] (http): Arduino bağlantı sağlık testi yapar.
- [[arduino_serial]] (registry): Arduino bağlantı sağlık testi yapar.
- [[camera]] (http): Kamera erişim ve stream testi yapar.
- [[camera]] (registry): Kamera erişim ve stream testi yapar.
- [[neopixel]] (http): `diagnostics` HTTP ile `neopixel` modülüne erişir: LED animasyon veya duygu preset uygular.
- [[ollama]] (registry): Ollama servis erişilebilirlik testi yapar.
- [[speak]] (http): `diagnostics` HTTP ile `speak` modülüne erişir: TTS servisinin hazır olup olmadığını kontrol eder.
- [[speech]] (http): `diagnostics` HTTP ile `speech` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[wakeword]] (http): `diagnostics` gateway veya doğrudan HTTP ile `wakeword` API'sini çağırır (calls path `/wakeword/status`).

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `diagnostics` modülünü import eder (`api`) — Sistem sağlık testi (Arduino, kamera, Ollama).
- [[gateway]] (import): `gateway` kod içinde `diagnostics` modülünü import eder (`config_loader`) — Sistem sağlık testi (Arduino, kamera, Ollama).
- [[scheduler]] (http): `scheduler` → `diagnostics`: Sistem sağlık kontrolü çalıştırır.
