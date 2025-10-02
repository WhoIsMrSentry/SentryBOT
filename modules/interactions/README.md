# Interactions Module

Durumlara/olaylara göre NeoPixel animasyonlarını otomatik seçen hafif bir kural motoru.

## Özellikler
- HTTP üzerinden mevcut NeoPixel servisine bağlanır (`/neopixel`).
- Base (sürekli) + Transient (kısa) efekt katmanı, öncelik ve cooldown ile.
- Sistem metrikleri: CPU sıcaklık/yük, ağ burst sezgisi.
- Olay besleme: `POST /interactions/event` ile (ör: `speech.start`, `error`).
- Donanım haritalama: Jewel (7) + Stick (16 tek sıra). Şimdilik tüm strip’e animasyon uygular.

## Kurulum
- FastAPI uygulaması: `xInteractionsService.create_app()`.
- Varsayılan port: 8095 (`config/config.yml`).

## API
- GET `/interactions/state`: aktif base/effect ve son metrikler.
- POST `/interactions/event` `{ type, data? }`: olay tetikle (ör: `speech.start`).
- POST `/interactions/effect` `{ name, duration_ms? }`: manuel kısa efekt.
- POST `/interactions/base` `{ name, color? }`: geçici base override.

### Gateway Entegrasyonu
Gateway, `interactions` router’ını tek portta sunar. NeoPixel uçları da gateway’de açıksa, kurallar doğrudan bu uçlara istek gönderir; modülü ayrı başlatmaya gerek yoktur.

## Varsayılan Davranış (config.yml)
- Sıcaklık ≥ 75°C: BREATHE kırmızı (base, high)
- 65–74°C: PULSE turuncu (base, medium)
- CPU yük ≥ 0.9: PULSE sarı (base, medium)
- Ağ burst: COMET 800ms (transient, cooldown 3s)
- speech.start: RAINBOW_CYCLE 1s (transient)
- speech.end: COMET 600ms (transient)
- Arduino disconnected: THEATER_CHASE magenta (base, high)
- error: METEOR 500ms (critical, cooldown 10s)
- warning: PULSE 400ms (high, cooldown 3s)
- Hiçbiri değilse: BREATHE teal (idle base)

## Kural/Config Yapısı
`modules/interactions/config/config.yml`
- `adapter.http_base_url`: NeoPixel HTTP tabanı (varsayılan: `http://localhost:8092/neopixel`).
- `hardware.segments`: Jewel + Stick tanımı (ileri geliştirme için hazır).
- `thresholds`: cpu_temp/cpu_load/net burst eşikleri.
- `rules`: sıralı değerlendirilir. Koşullar (örnek anahtarlar):
  - `event`, `cpu_temp_gte`, `cpu_temp_lt`, `cpu_load_gte`, `net_burst`, `arduino_connected`
- `defaults.idle`: boşta gösterilecek base animasyon.

### Yeni Uyarı/Etkileşim Ekleme
1. `rules` listesine yeni bir kural ekleyin:
```yaml
- id: my_custom
  when: { event: my.event }
  action: { effect: { name: COMET, duration_ms: 700 } }
  priority: high
  cooldown_ms: 2000
```
2. Olayı gönderin:
```json
POST /interactions/event
{ "type": "my.event" }
```
3. Renge özel davranmak isterseniz `base.color: "#RRGGBB"` verebilirsiniz (uyumlu animasyonlarda dolgu yapılır, aksi halde animasyon adı oynatılır).

## Notlar
- Quiet hours varsayılan olarak kapalıdır (isteğe göre eklenebilir).
- NeoPixel servisi yoksa istekler sessizce yok sayılır (No-Op mod).
- İleride segment/mask desteklemek için NeoPixel API genişletimi önerilir.

---
Bu modül DryCode prensiplerine uygundur: tek sorumluluklu dosyalar, config odaklı, sade API.
