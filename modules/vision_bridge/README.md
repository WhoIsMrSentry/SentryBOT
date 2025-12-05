# Vision Bridge Module

Kamera akışını işleyen yerel (Pi5) veya uzak (dizüstü / sunucu) görüntü işleme pipeline sonucunu robota ve diğer modüllere köprüler.

## Modlar
- **local**: Pi5 üzerinde hafif YOLO + yüz tanıma (varsa) çalışır.
- **remote**: Harici cihaz video akışını işler, sonuçları köprüye POST eder. Pi üzerinde ağır model yüklenmez.

`config.yml` içinde `vision.processing_mode: local|remote` ile seçilir.

## Endpoints
- `POST /vision/track { head_tilt, head_pan, drive? }` : Arduino "track" komutu.
- `POST /vision/analyze` : Tek kare analiz (yalnızca local).
- `GET  /vision/video_feed` : Annotated MJPEG akışı (yalnızca local).
- `GET  /vision/results/latest` : Son işlenen karedeki nesne/kişi listesi (autonomy vb. modüller bu uçtan beslenebilir).
- `POST /vision/results` : Uzak işlemciden obje/kisi tespiti sonuçları (remote veya her iki mod). Header: `X-Auth-Token`.
- `POST /vision/blind/start` / `stop` : Görme engelli modu açıklama.
- `POST /vision/faces/register` / `GET /vision/faces` : Yüz kayıt & liste (local).
- `POST /vision/memory/chat` : `{ person, text, role? }` kişi hafızasına sohbet satırı ekler.
- `GET  /vision/memory/person?person=Alice` : kişinin hafızası (son özet + sohbetler).
- `GET  /vision/memory/people` : hafızada kayıtlı isimler.
- (Plan) `POST /vision/mode` : Çalışma modları arasında geçiş (objects/people/ocr/depth...).

### /vision/results Payload Örneği
```json
{
  "frame_id": 123,
  "timestamp": 1733123123.12,
  "objects": [
    {"label": "person", "confidence": 0.91, "bbox": [10,20,180,400], "distance_m": 1.6, "name": "Alice"},
    {"label": "chair", "confidence": 0.78, "bbox": [220,100,320,360]}
  ]
}
```

## Güvenlik
- `remote.auth_token` yapılandırıldıysa `X-Auth-Token` eşleşmelidir.
- `remote.accept_results: false` ile dış sonuç kabulü kapatılabilir.

## Blind Mode (Assistive)
Aktifken semantik sahne özeti (Ollama varsa LLM tabanlı) ve kişilere özel selam gönderir. Uzak modda gelen sonuçlar üzerinden de çalışır.

## Çalıştırma
- Bağımsız: `python -m modules.vision_bridge.xVisionBridgeService`
- Gateway ile: `python -m modules.gateway.xGatewayService` ve `include.vision_bridge: true`

## Gelecek Genişletmeler
- Derinlik / mesafe için stereo / mono depth entegrasyonu (remote).
- Metin okuma (OCR) sonuç formatı genişletmesi: `objects[].text` alanı.
- Tehlike uyarıları için tür eşik konfigürasyonu.
- Duygusal durum geri bildirimi: `interactions` modülü ile LED / ses.

### Liveliness Starter (opsiyonel)
`modules/vision_bridge/tools/liveliness_starter.py` basit heartbeat ve idle lookaround döngüsü sağlar.
Gateway açıkken çalıştırılabilir ve `interactions` ile `vision/track` uçlarını kullanır.
