# Gateway

SentryBOT'un tek FastAPI sürecinde tüm modül router'larını birleştiren ana giriş kapısıdır. Üretim modunda robot tek port üzerinden hizmet verir.

## Sorumluluklar

- Modül router'larını mount etme ve başlatma (`bootstrap`)
- Merkezi sağlık, durum ve derin sağlık kontrolü
- İsteğe bağlı API anahtarı ve rol tabanlı güvenlik katmanı
- Modüller arası kablolama: Arduino↔NeoPixel, VLM↔Autonomy, Speech↔Interactions vb.
- `resolve_gateway_base_url` ile loopback URL çözümleme (25+ modül tarafından kullanılır)

## Mimari

- Giriş noktası: `xGatewayService.py`
- Bootstrap: `services/bootstrap.py`
- Çekirdek router: `api/router.py`
- URL yardımcıları: `url.py`
- Konfigürasyon: `config/config.yml` + `config/agent.yaml` birleşimi

## Bootstrap Davranışı

`bootstrap(app, cfg)` modülleri `include.<module>` bayraklarına göre yükler.

Varsayılan açık modüller:
- `social_db`
- `agent_core`
- `admin_ui` (varsayılan: true)

Kritik modüller (mount hatası `error` seviyesinde loglanır):
- `arduino`, `camera`, `autonomy`, `agent_core`, `speech`, `wakeword`, `speak`, `ollama`

Import-tabanlı mount edilen modüller:
- `mutagen`, `ota`, `hardware`, `telemetry`, `diagnostics`, `calibration`

Opsiyonel mount:
- `state_manager`, `scheduler`, `config_center`

Bootstrap sonrası kablolama:
- `_wire_arduino_neopixel`
- `_wire_arduino_autonomy`
- `_wire_vlm_autonomy`
- `_wire_onsensor_vlm`
- `_wire_interactions_piservo`
- `_wire_wakeword_interactions`
- `_wire_speech_interactions`

## API

- `GET /healthz` — startup durumu + modül bazlı sağlık
- `GET /status` — include/start farkı
- `GET /health` — derin sağlık taraması (httpx varsa)

Mount edilen modüller kendi prefix'leri altında yayınlanır (`/speech/*`, `/autonomy/*`, `/arduino/*`, `/config/*` vb.).

## Konfigürasyon

`modules/gateway/config/config.yml`:
- `server.host`, `server.port`
- `include.*` — modül aç/kapa
- `security.enabled`, `security.api_key`, `security.admin_roles`

Güvenlik etkinse yazma uçları `X-API-Key` bekleyebilir; admin prefix'leri ek rol kontrolü uygular.

## Çalıştırma

```bash
python -m modules.gateway.xGatewayService
```

## İlişkiler

Gateway, projedeki modüller arası entegrasyonun omurgasıdır. Diğer modüller bağımsız servis olarak da çalışabilir; ancak Pi5 üretim senaryosunda gateway tek süreç modelini sağlar.
