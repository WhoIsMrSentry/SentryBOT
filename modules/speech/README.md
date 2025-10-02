# Speech Module (Offline I2S + DoA + Tracking)

Raspberry Pi 5 üzerindeki I2S/ALSA mikrofonlardan ses alır, Vosk ile tamamen offline konuşma tanıma yapar, iki mikrofonla ses geliş yönünü (DoA) hesaplar ve pan-tilt izleme için hedef açı üretebilir.

## Özellikler
- I2S/ALSA yakalama (sounddevice/PortAudio)
- Offline ASR (Vosk) – internet gerekmez
- İsteğe bağlı WebRTC VAD ön filtresi
- Çift mikrofonla yön tayini (GCC-PHAT, -90°..+90°)
- Sinyal kararlılığı için enerji eşiği, ölü bant, yumuşatma, slew-rate sınırı
- Pan-tilt izleme döngüsü ve kolay donanım entegrasyonu (callback)
- FastAPI ile servis; modül olarak import edilebilir

## Kurulum
1) Bağımlılıklar (Python)
    - sounddevice (PortAudio/ALSA)
    - vosk
    - fastapi, uvicorn (API için)
    - (opsiyonel) webrtcvad — VAD kullanacaksanız

2) Sistem gereksinimleri
    - RPi’de ALSA/PortAudio. I2S mikrofonun `arecord -l` veya `sd.query_devices()` ile görünmesi gerekir.

3) Vosk model(ler)i
    - Modeller: https://alphacephei.com/vosk/models
    - Örnek: `modules/speech/models/vosk-tr/`
    - Ya `recognition.model_path` ile tam yol verin ya da `recognition.language` seçin, otomatik eşleme kullansın.

## Hızlı Başlangıç
### Kütüphane
```python
from modules.speech.xSpeechService import SpeechService
svc = SpeechService()
svc.start_background(on_result=lambda r: print(r))
```

### CLI
```powershell
python -m modules.speech.xSpeechService --listen-once
# veya API
python -m modules.speech.xSpeechService --api --config modules/speech/config/config.yml
```

### Servis (FastAPI)
```python
from fastapi import FastAPI
from modules.speech.xSpeechService import SpeechService
from modules.speech.api import get_router

svc = SpeechService()
app = FastAPI()
app.include_router(get_router(svc))
```

## HTTP API Uç Noktaları
- POST `/speech/start` – Arka planda dinlemeyi başlatır
- POST `/speech/stop` – Dinlemeyi durdurur
- GET `/speech/last` – Son kısmi/nihai tanıma sonucu `{ text, final, confidence }`
- GET `/speech/direction` – Son hesaplanan açı `{ angle }` (yoksa 503)
- POST `/speech/track/start` – Pan-tilt izlemeyi başlatır
- POST `/speech/track/stop` – Pan-tilt izlemeyi durdurur
- GET `/speech/track/status` – `{ active, current, target, min, max, tracking, angle }`

## Yapılandırma (config.yml) – Referans
Dosya: `modules/speech/config/config.yml`

### server
- `host`: API servis adresi (vars: `0.0.0.0`)
- `port`: API portu (vars: `8082`)

### audio
- `device`: ALSA cihaz adı veya index (null=default)
- `samplerate`: Önerilen 16000 (VAD için 8/16/32/48k geçerli)
- `channels`: 1=mono, 2=stereo (DoA için 2 gerekir)
- `dtype`: PCM formatı (vars: `int16`)
- `frame_ms`: Çerçeve süresi ms (vars: 30)

### recognition
- `language`: Dil kodu (tr, en, en-us, de, es, fr, ...)
- `model_path`: Mutlak/bağıl model klasörü (dilden önceliklidir)
- `language_models`: Dil -> model klasör eşlemesi (bağıl yollar modül köküne göre çözülür)
- `samplerate`: Vosk örnekleme hızı (vars: 16000)
- `max_alternatives`: 0=kapalı; >0 ise alternatif hipotez sayısı
- `vad.enabled`: true/false – WebRTC VAD ön filtresi
- `vad.aggressiveness`: 0..3 – 3 en agresif
- `vad.hangover_ms`: Konuşma bittikten sonra tutulacak süre (ms)

Davranışlar:
- `model_path` verilirse kullanılır; verilmezse `language` ile `language_models` üzerinden otomatik seçilir.
- Stereo giriş DoA için kullanılır, ASR için akış dahili olarak mono’ya indirgenir.

### direction
- `enabled`: true/false – Yön tahmini (stereo şart)
- `mic_distance_m`: Mikrofonlar arası mesafe (m)
- `control.invert_direction`: Sol/Sağ kablolama ters ise işareti çevirir
- `control.deadband_deg`: Ölü bant (küçük değişimleri yok say)
- `control.smoothing_alpha`: 0..1 EMA düşük geçiş filtresi
- `control.slew_deg_per_s`: Saniyedeki azami açı değişimi
- `control.energy_threshold`: RMS eşiği; altındaysa açı güncellenmez

Yön hesaplama: GCC-PHAT ile örnek gecikme (TDoA) bulunur, geometriyle -90..+90° aralığına dönüştürülür, ardından kontrol filtreleri uygulanır.

### pan_tilt
- `enabled`: true/false – Kontrolcü hazır (takip ayrı bayraktır)
- `center_deg`: Nötr pan açısı (genelde 90)
- `min_deg` / `max_deg`: Çalışma sınırları
- `slew_deg_per_s`: Azami yaklaşım hızı
- `update_hz`: Gönderim döngüsü frekansı

Takip mantığı: Takip açıkken hedef pan = `center_deg + angle`. Slew limitiyle akıcı güncellenir ve `sender` callback’i ile donanıma iletilir.

## CLI Bayrakları
- `--config <path>`: Farklı bir config dosyası kullan
- `--listen-once`: İlk nihai sonucu alıp çıkar
- `--api`: FastAPI sunucusunu konfigdeki host/port ile çalıştır

## Donanım Entegrasyonu (Pan-Tilt)
`PanTiltController`, açıları `sender(angle_deg)` callback’i ile iletir. Varsayılan sender log yazar. Donanıma bağlamak için `xSpeechService.py` içindeki `_send_pan` fonksiyonunu seri/HTTP vb. ile değiştirin.

Örnek (seri):
- Arduino: “PAN:<deg>\n” formatını dinlesin.
- Python: `_send_pan` içinde seri porta yazın (pyserial ile).

## Sorun Giderme
- `sounddevice not available`: `pip install sounddevice`; RPi’de ALSA cihazlarını doğrulayın.
- `Vosk model directory not found`: `recognition.model_path` veya `language_models` yolu hatalı.
- `VAD enabled but 'webrtcvad' is not installed`: `pip install webrtcvad` (opsiyonel).
- `/speech/direction` 503: Stereo yok veya yön henüz hesaplanmadı.

## Örnek Konfig (özet)
```yaml
server:
   host: 0.0.0.0
   port: 8082

audio:
   samplerate: 16000
   channels: 2
   frame_ms: 30

recognition:
   language: tr
   language_models:
      tr: models/vosk-tr
   vad:
      enabled: false

direction:
   enabled: true
   mic_distance_m: 0.06
   control:
      invert_direction: false
      deadband_deg: 3.0
      smoothing_alpha: 0.3
      slew_deg_per_s: 120.0
      energy_threshold: 1000

pan_tilt:
   enabled: true
   center_deg: 90
   min_deg: 0
   max_deg: 180
   slew_deg_per_s: 120
   update_hz: 20
```

## Notlar
- Mono girişte yön tahmini otomatik devre dışıdır; tanıma çalışmaya devam eder.
- DoA açısı pozitifse sağ, negatifse sol kabul edilir; `invert_direction` kablo yönünü telafi eder.

## Gateway ile Kullanım
Gateway çalışırken `speech` API uçları tek portta `/speech/*` altında sunulur.
