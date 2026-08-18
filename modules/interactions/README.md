# Interactions

Durumlara ve olaylara göre ışık/ifade tepkisi üreten hafif kural motorudur. `InteractionEngine`, sistem metriklerini ve olay akışlarını dinler; NeoPixel tarafına base ve transient efektler uygular.

## Sorumluluklar

- Olay tabanlı efekt tetikleme: `speech.start`, `speech.end`, `error`, benzeri özel event'ler
- CPU sıcaklığı, CPU yükü ve ağ patlaması gibi sistem sinyallerinden görsel tepki üretme
- Manual base override ve tek seferlik efekt yürütme
- Quiet-hours sırasında rahatsız edici efektleri baskılama
- Gateway URL çözümlemesi ile loopback adreslerini tek port mimariye uyarlama

## Mimari

- Giriş noktası: `xInteractionsService.py`
- Router: `api/router.py`
- Motor: `services/engine.py`
- Kurallar: `services/rules.py`
- Metrikler: `services/metrics.py`
- Adaptör: `services/adapters/neopixel_client.py`

## Bağımlılıklar

- `gateway.url`: loopback URL'lerini yeniden yazma
- `neopixel`: HTTP adaptörü üzerinden efekt gönderimi
- `hardware`: sistem metrikleri kaynağı
- `social_db`: varsayılan profil/veri desteği

## API

Gateway altında `/interactions/*` olarak yayınlanır.

- `GET /interactions/state`
- `POST /interactions/event`
- `POST /interactions/effect`
- `POST /interactions/base`

`/interactions/effect` çağrısı ayrıca `color`, `r/g/b`, `force` ve `emotions` alanlarını destekler.

## Konfigürasyon

Varsayılanlar `config_loader.py` içinde tanımlıdır ve modül-içi `config/config.yml` ile birleştirilir.

- `adapter.http_base_url`
- `hardware.num_leds`, `hardware.segments`
- `thresholds.cpu_temp`, `thresholds.cpu_load`, `thresholds.net`
- `defaults.idle`
- `rules`
- `quiet_hours`

## İlişkiler

Bu modül özellikle `speech`, `autonomy`, `logwrapper`, `scheduler` ve `vlm_bridge` gibi üretici modüllerden gelen olayları görsel tepkiye dönüştürmek için bir ara katman görevi görür. Otonomluğun sahneleme tarafında yardımcı bir altyapıdır; kendi başına karar vermez ama kararların dışa vurumunu standardize eder.
