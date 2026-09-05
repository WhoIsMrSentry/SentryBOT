# Expression

SentryBOT'un semantik ifade orkestrasyon modülüdür. Sistem olaylarını ve duygu komutlarını LED, OLED, ses, kafa ve kulak modalitelerine atomik biçimde dağıtır.

## Sorumluluklar

- Olay → semantik ifade durumu eşlemesi (`SemanticExpressionEngine`)
- Çoklu modalite koordinasyonu (`ExpressionArbiter`) - **Lease tabanlı arbitraj**
- LLM tool endpoint'i: `/expression/express`
- `common.emotion_vocab` tabanlı render sözlüğü
- Output bridge ile legacy hedeflere uygulama

## Mimari (Güncel: 2026-08-20)

- Giriş noktası: `xExpressionService.py` (thin facade, <100 satır)
- **Semantik Motor**: `services/state.py` → `SemanticExpressionEngine` + `services/state_events.py`
- **Arbiter**: `services/arbitrator.py` → `ExpressionArbiter` (priority lease, visual lock, modality clients)
- **Çıkış Köprüsü**: `services/output_bridge.py` → Legacy hedeflere plan/apply
- **Adapters**: `services/adapters/head_adapter.py` (kafa kontrolü)
- **Router**: `semantic/api/router.py` (kök `api/router.py` artık 2 satırlık re-export shim)

### Alt Modüller (Expression Kapsamında)

| Alt Modül | Yol | Sorumluluk |
|-----------|-----|------------|
| **Animate** | `expression/animate/` | YAML tabanlı servo sekansları (sit, blink, look_around, owner_scan, vb.) |
| **Piservo** | `expression/piservo/` | Kulak servo jestleri (PWM/I2C), duygu→kulak pozisyonu |
| **Interactions** | `expression/interactions/` | Kural tabanlı NeoPixel/LED efekt tetikleme (CPU, network, events) |

Graph'ta gateway `_include_expression` `xExpressionService` oluşturur ve `router.set_arbiter(...)` ile `/express` yolunu bağlar. `voice/speak` modülü `speak.started/finished` olaylarını expression katmanına gönderir.

## API (Gateway altında `/expression/*`)

### Durum
- `GET /expression/state`
- `GET /expression/status`
- `GET /expression/history`

### Olay / Manuel
- `POST /expression/event`
- `POST /expression/state`
- `POST /expression/output/apply`

### Atomik İfade (LLM Tool)
- `POST /expression/express`
  - `emotion`, `intensity`, `duration_s`
  - `modalities`: `leds`, `oled`, `voice`, `head`, `ears`
  - opsiyonel `text`, `language`, `force`

### Sözlük
- `GET /expression/vocab`
- `GET /expression/render/{emotion}`

### Output Bridge (Legacy)
- `GET /expression/output/status`
- `GET /expression/output/plan`
- `POST /expression/output/apply`

## Konfigürasyon

Modül-içi `config/config.yml` + merkezi `config/agent.yaml` (expression section):
- Olay → ifade eşleme kuralları (`event_map`)
- Modality client URL'leri (`adapters.gateway_url`)
- Rate limit / visual lock ayarları (`visual_lock_ms`, `min_interval_ms`)

## İlişkiler (Güncel Modül Yolları)

**Çıkış Modaliteleri (Arbiter Client'ları):**
- `visual_output/neopixel` → LED animasyonları, companion modes
- `visual_output/oled_faces` → OLED göz ifadeleri, mood/activity render
- `expression/piservo` → Kulak servo jestleri
- `arduino_serial` → Kafa hareketi (head_adapter üzerinden, **HeadControlArbiter lease zorunlu**)
- `voice/speak` → TTS prosody (tone, rate, pitch)

**Olay Kaynakları:**
- `expression/interactions` → Metrik olaylar (CPU, network, companion)
- `autonomy` → Mood, idle action, companion goal olayları
- `voice/speak` → `speak.started`, `speak.finished` (ses senkronizasyonu)
- `vlm_bridge` → Vision focus, person detected
- `voice/wakeword` → Wakeword detected

**Ortak Sözlük:**
- `common.emotion_vocab` → Tek duygu taksonomisi (canonical name, render hints, valence, arousal)

## ExpressionArbiter Lease Sistemi (KRİTİK)

Tüm donanım modaliteleri (LED, OLED, Servo/Head, Ears) **lease** alır:
```python
arbiter.claim_lights(source="autonomy", priority=80, ttl_s=2.0, force=False)
arbiter.claim_servo(source="animate", priority=90, ttl_s=1.5)
arbiter.claim_oled(source="autonomy", priority=70)
```
- `priority`: Yüksek kazanır (animate=90, autonomy=80, interactions=60)
- `ttl_s`: Otomatik release süresi
- `force`: Mevcut lease'i ez (dikkatli kullan)

## Kanonik Ağaç Notu

`semantic/` altındaki uygulama **kanoniktir** ve kök `xExpressionService.py` shim'i üzerinden mount edilir. `services/` altındaki eski ağaç yalnızca testlerin kullandığı legacy bir kopyadır ve birleştirme planındadır.

## Bilinen Sorunlar

1. **HeadControlArbiter Bypass** - `expression/animate` ve `autonomy` doğrudan `arduino.track()` çağırıyor, `ExpressionArbiter` lease alıyor ama `HeadControlArbiter` (vlm_bridge) ayrı bir sistem. **İki arbiter birleştirilmeli.**

## Çözülen Sorunlar

- ~~**xExpressionService Çok Büyük** (4209 satır)~~ — ✅ ÇÖZÜLDÜ: Kök `xExpressionService.py` artık 2 satırlık shim; kanonik implementasyon `semantic/` ağacında.