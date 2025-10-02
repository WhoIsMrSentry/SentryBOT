# Speak (TTS) Module

Küçük, tek sorumluluklu bileşenler (DryCode). Hem kütüphane hem servis olarak çalışır.

## Özellikler
- TTS motorları: pyttsx3 (offline), Piper (harici ikili/model; offline, doğal)
- MAX98357A I2S amplifikatör üzerinden ses çıkışı (ALSA cihazı)
- Harici ses çalma: base64 WAV veri oynatma
- Temiz API: `/speak/say` (TTS) ve `/speak/play` (codec + base64)
- Modüler yapı: TTS, Player, Decoder ayrık ve test edilebilir

## Hızlı Başlangıç
### Python
```python
from modules.speak import SpeakService
svc = SpeakService()
svc.speak("Merhaba dünya")
```

### CLI / Servis
- Çalıştır: `python -m modules.speak.xSpeakService --api`
- TTS: POST `/speak/say` body: {"text":"Merhaba"}

## API
- GET `/speak/status` → { ready: true }
- POST `/speak/say`
	- Body: `{ "text": "...", "engine": "pyttsx3|piper" }` (engine opsiyonel)
	- Dönüş: `{ ok, engine, duration_sec, samplerate }`
- POST `/speak/play`
	- Body: `{ "data": "<base64-wav>" }`
	- Dönüş: `{ ok, duration_sec }`

## Yapılandırma (config/config.yml)
```yaml
server:
	host: 0.0.0.0
	port: 8083

audio_out:
	device: null          # ALSA cihaz (örn. hw:1,0)
	samplerate: 22050
	channels: 1           # MAX98357A mono; driver stereo ise kod upmix yapar
	dtype: float32

tts:
	engine: pyttsx3       # pyttsx3 | piper | dummy
	language: tr
	voice: null
	rate: 170
	volume: 1.0
	samplerate: 22050
	piper:
		bin_path: piper           # PATH’te yoksa tam yol
		model_path: null          # gerekli, .onnx/.onnx.gz
		samplerate: 22050
		speaker: null
		length_scale: null
		noise_scale: null
		noise_w: null

```

## Donanım ve Kurulum Notları
- MAX98357A I2S DAC ALSA’da bir çıkış cihayı olarak görünmelidir.
- `aplay -l` ile kartı bulun ve `audio_out.device` içine yazın (örn. `hw:1,0`).
- Piper için:
	- Piper binary ve uygun dil modeli (örn. Türkçe) indirilmelidir.
	- `tts.engine: piper` ve `tts.piper.model_path` ayarlanmalıdır.
- Opus ve diğer kodekler için ffmpeg gereklidir.

## Bağımlılıklar
- Python: `sounddevice`, `soundfile`, `numpy`, (opsiyonel) `pyttsx3`
- Harici: `piper` (TTS ikilisi) + model, `ffmpeg` (decode) 

## Test
- Minimal smoke test: `tests/test_smoke.py`

## Gateway ile Kullanım
Gateway çalışırken TTS uçları tek portta `/speak/*` altında sunulur; modülü ayrı servis olarak başlatmaya gerek yoktur.