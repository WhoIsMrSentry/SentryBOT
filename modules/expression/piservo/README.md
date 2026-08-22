# PiServo (Ears)

İki servo ile robot kulak hareketlerini yönetir. Duygu, olay ve jest sinyallerini fiziksel kulak pozlarına çevirir.

## Sorumluluklar

- Sol/sağ kulak açı kontrolü (0–180°)
- Duygu → kulak pozu eşlemesi (`EMOTION_POSES` + `common.emotion_vocab`)
- Jestler: `wakeword`, `sound`
- Çoklu backend: Arduino (varsayılan), pigpio, sim

## Mimari

- Giriş noktası: `xPiServoService.py`
- Koordinatör: `services/runner.py` (`EarRunner`)
- Sürücü: `services/driver.py` (`Servo`, `ServoConfig`)
- Duygu tablosu: `services/ears.py`

Gateway `_include_piservo` ile mount edilir. Arduino modülü aktifken `arduino_index` config'ten çıkarılır; GPIO değeri PCA9685 kanal indeksi olarak kullanılabilir.

## API (Gateway altında `/piservo/*`)

- `GET /piservo/healthz`
- `POST /piservo/set?left=90&right=90`
- `POST /piservo/emotion?name=joy`
- `POST /piservo/gesture?name=wakeword|sound`
- `POST /piservo/event?kind=...` (gesture alias)

## Duygu Eşlemesi

`neutral`, `joy`, `fear`, `anger`, `sadness`, `surprise`, `curiosity` — ayrıca `emotion_vocab` alias'ları (happy, sleepy vb.) otomatik çözülür.

## Konfigürasyon

`config/config.yml`:
```yaml
left:
  gpio: 12
  arduino_index: 2   # Arduino backend kanalı
right:
  gpio: 13
  arduino_index: 3
```

Robot kafa pan/tilt Arduino'da indeks 0/1; kulaklar genelde 2/3.

## İlişkiler

- `interactions`: `_wire_interactions_piservo` — wakeword, vision, emotion olayları
- `expression`: `ExpressionArbiter` → `PiServoAdapter.set_ears`
- `wakeword`, `speech`: dolaylı jest tetikleme
- `common.emotion_vocab`: kanonik duygu çözümlemesi

Otonomlukta duygusal durumun fiziksel kulak ifadesi katmanıdır.
