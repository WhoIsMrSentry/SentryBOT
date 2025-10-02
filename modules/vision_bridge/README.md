# Vision Bridge Module

Dış işleyici (PC) için basit API köprüsü. PC, kamera akışını işledikten sonra robota komutu HTTP ile gönderir.

## Endpoint
- POST /vision/track { head_tilt, head_pan, drive? }
  - Arduino firmware "track" komutuna köprüler.

## Çalıştırma
- Bağımsız: `python -m modules.vision_bridge.xVisionBridgeService`
- Gateway ile: `python -m modules.gateway.xGatewayService` ve include.vision_bridge: true olmalı.
