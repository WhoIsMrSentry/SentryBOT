# Speak module config

- server: FastAPI sunucu ayarları
- audio_out: ALSA üzerinden çıkış ayarları (I2S MAX98357A)
- tts: TTS motor ayarları (pyttsx3 veya dummy)

MAX98357A ile kullanım:
- Raspberry Pi'de I2S'i etkinleştirin ve doğru ALSA cihazını `aplay -l` ile bulun.
- `device` alanına uygun isim/index girin (örn. `hw:1,0`).
