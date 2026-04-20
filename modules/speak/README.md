# Speak (TTS) Module

Küçük, tek sorumluluklu bileşenler (DryCode). Hem kütüphane hem servis olarak çalışır.

## Özellikler
- TTS motorları: pyttsx3 (offline), Piper (harici ikili/model; offline, doğal)
- Uzak TTS: Piper ve XTTS için tek endpoint + engine parametresi desteği
- MAX98357A I2S amplifikatör üzerinden ses çıkışı (ALSA cihazı)
- Harici ses çalma: base64 WAV veri oynatma
- Konuşma sırasında canlılık senkronu: `/interactions/event` ve `/interactions/effect` ile LED tepkisi
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
	- Body: `{ "text": "...", "engine": "pyttsx3|piper|xtts", "tone": { "rate": 190, "volume": 0.9 } }`
	- `tone` alanı opsiyoneldir; `rate`, `volume` veya `piper` içindeki `length_scale`, `noise_scale` gibi ayarları anlık olarak override edebilirsiniz.
	- Dönüş: `{ ok, engine, duration_sec, samplerate }`
- POST `/speak/play`
	- Body: `{ "data": "<base64-wav>" }`
	- Dönüş: `{ ok, duration_sec }`

## Yapılandırma (config/agent.yaml -> speak)
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
	engine: piper         # pyttsx3 | piper | xtts | dummy
	language: tr
	voice: null
	rate: 170
	volume: 1.0
	samplerate: 22050
	remote:
		enabled: true
		endpoint: http://<tts-host>:5000/tts/synthesize
		timeout: 120
		auth_token: ""
	piper:
		bin_path: piper           # PATH’te yoksa tam yol
		model_path: null          # gerekli, .onnx/.onnx.gz
		samplerate: 22050
		speaker: null
		length_scale: null
		noise_scale: null
		noise_w: null
	xtts:
		endpoint: http://<tts-host>:5000/tts/synthesize
		timeout: 120
		language: tr
		speaker_wav: null

liveliness:
	enabled: true
	interactions_base_url: http://localhost:8080/interactions
	speech_effect:
		name: PULSE
		tone_effect_map:
			fast: COMET
			neutral: PULSE
			calm: BREATHE
			tired: THEATER_CHASE
		min_duration_ms: 400
		max_duration_ms: 7000
		chars_per_second: 16
		force: false

```

Not: Speak modülü artık modül içi config/config.yml okumaz. Kaynak dosya config/agent.yaml içindeki speak bölümüdür.

## Uzak TTS Sözleşmesi (tek endpoint)
Uzak çağrıda aşağıdaki JSON gönderilir:

```json
{
	"text": "Merhaba",
	"engine": "piper",
	"language": "tr",
	"speaker_wav": "/path/ref.wav",
	"piper": {},
	"xtts": {}
}
```

Yanıt olarak ya doğrudan audio/wav baytları ya da base64 ses içeren JSON beklenir.

`liveliness.enabled: true` iken `speak` akışı otomatik olarak:
- konuşma başında `speech.start` event gönderir,
- metin uzunluğu ve tone bilgisine göre efekt süresi hesaplayıp `/interactions/effect` tetikler,
- konuşma bitince `speech.end` event gönderir.

`tone_effect_map` sayesinde konuşma tonu (`rate`/`volume`) farklı efektlere eşlenebilir.
`emphasis_effect_map` ile `!` ve `?` gibi vurgu işaretleri için kısa ek efektler gönderilir.
`rhythm` bloğu ile metin uzunluğuna göre beat sayısı hesaplanıp mikro efekt vuruşları üretilir.

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