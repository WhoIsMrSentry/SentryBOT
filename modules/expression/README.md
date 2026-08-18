# Expression

SentryBOT'un semantik ifade orkestrasyon modülüdür. Sistem olaylarını ve duygu komutlarını LED, OLED, ses, kafa ve kulak modalitelerine atomik biçimde dağıtır.

## Sorumluluklar

- Olay → semantik ifade durumu eşlemesi (`SemanticExpressionEngine`)
- Çoklu modalite koordinasyonu (`ExpressionArbiter`)
- LLM tool endpoint'i: `/expression/express`
- `common.emotion_vocab` tabanlı render sözlüğü
- Output bridge ile legacy hedeflere uygulama

## Mimari

- Giriş noktası: `xExpressionService.py`
- Semantik motor: `services/state.py` (`SemanticExpressionEngine`)
- Arbiter: `services/arbitrator.py` (`ExpressionArbiter`)
- Çıkış köprüsü: `services/output_bridge.py`
- Router: `api/router.py`

Graph'ta `SemanticExpressionEngine` gateway bootstrap (`_include_expression`) ile başlatılır. `speak` modülü `speak.started/finished` olaylarını expression katmanına gönderir.

## API (Gateway altında `/expression/*`)

### Durum
- `GET /expression/healthz`
- `GET /expression/state`
- `GET /expression/status`
- `GET /expression/history`

### Olay / Manuel
- `POST /expression/event`
- `POST /expression/state`
- `POST /expression/apply` (legacy)

### Atomik İfade (LLM tool)
- `POST /expression/express`
  - `emotion`, `intensity`, `duration_s`
  - `modalities`: `leds`, `oled`, `voice`, `head`, `ears`
  - opsiyonel `text`, `language`, `force`

### Sözlük
- `GET /expression/vocab`
- `GET /expression/render/{emotion}`

### Output Bridge (legacy)
- `GET /expression/output/status`
- `GET /expression/output/plan`
- `POST /expression/output/apply`

## Konfigürasyon

Modül-içi `config/config.yml`:
- olay → ifade eşleme kuralları
- modality client URL'leri
- rate limit / visual lock ayarları

## İlişkiler

- `neopixel`, `oled_faces`, `speak`, `piservo`, `arduino_serial`: çıkış modaliteleri
- `interactions`, `autonomy`, `speak`: olay kaynakları
- `common.emotion_vocab`: tek duygu taksonomisi

Otonomlukta kararın fiziksel ve duygusal dışa vurumunu senkronize eden ifade katmanıdır.
