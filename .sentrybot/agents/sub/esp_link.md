# Sub-Agent: esp_link-specialist

## Uzmanlık
`xEspLinkService` ve `esp_link` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/esp_link.md`

## Bileşen haritası
- `xEspLinkService` — modules/esp_link/xEspLinkService.py

## Dış bağlantılar (neden)
- [[config_center]] (import): `esp_link` → `config_center`: config/agent.yaml dosyasından ayar okur.

## Gelen bağlantılar (neden)
- [[gateway]] (import): `gateway` kod içinde `esp_link` modülünü import eder (`xEspLinkService`) — ESP32 köprü iletişimi (mDNS web remote).
- [[gateway]] (import): `gateway` kod içinde `esp_link` modülünü import eder (`api`) — ESP32 köprü iletişimi (mDNS web remote).
