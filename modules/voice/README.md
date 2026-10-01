# SentryBOT V5 — Ses Alt Sistemi (`modules/voice`)

SentryBOT'un çift yönlü tüm işitsel etkileşimini, donanım çoklamasını, uyanma kelimesi tespitini, yön tayinini (DoA), konuşma tanımayı (STT) ve konuşma sentezini (TTS) yöneten merkezi alt sistemdir.

---

## 🚀 Hızlı Başlangıç

### 1. Bağımlılıklar

Ses alt sistemi için temel sistem ve Python kütüphaneleri:
- **PortAudio & PyAudio:** Düşük gecikmeli donanım ses yakalama/oynatma.
- **ONNX Runtime:** Piper TTS ve openWakeWord çıkarımı.
- **Faster-Whisper / Vosk:** Çevrimdışı ve hızlı konuşma tanıma.

```bash
# Ubuntu / Raspberry Pi OS sistem bağımlılıkları:
sudo apt-get install -y portaudio19-dev libasound2-dev espeak-ng

# Python paketleri:
pip install pyaudio onnxruntime numpy faster-whisper piper-tts requests fastapi uvicorn
```

---

## 📂 Dizin Yapısı

```
modules/voice/
├── audio_router.py              # Singleton I2S/ALSA Ses Yakalama & Dağıtıcısı (EBUSY Önleyici)
├── architecture_voice.dot       # Graphviz Mimari Diyagram Kaynağı
├── architecture_voice.svg       # Derlenmiş Vektörel Mimari Şema
├── architecture_voice.md        # Kapsamlı Teknik & Sınıf Referansı
├── README.md                    # Bu doküman
├── speak/                       # TTS (Konuşma Sentezi) Servisi (Port: 8083)
│   ├── xSpeakService.py         # Piper ONNX TTS, Split-Lock, Düşünce Filtreleme
│   └── api/router.py            # /speak/say, /speak/say_stream, /speak/stop
├── speech/                      # STT (Konuşma Tanıma & DoA) Servisi (Port: 8084)
│   ├── xSpeechService.py        # Vosk/Whisper STT, GCC-PHAT Yön Tayini, Pan-Tilt
│   └── api/router.py            # /speech/start, /speech/stop, /speech/direction
└── wakeword/                    # WakeWord (Uyanma Kelimesi) Servisi (Port: 8085)
    ├── xWakewordService.py      # openWakeWord ONNX "hey sentry" Algılama
    └── api/router.py            # /wakeword/start, /wakeword/stop, /wakeword/status
```

---

## 🛠️ Alt Servisleri Çalıştırma

### 1. Speak (TTS) Servisini Başlatma
```bash
python -m modules.voice.speak.xSpeakService --api
# veya tek komut test:
python -m modules.voice.speak.xSpeakService "Merhaba, ben SentryBOT!"
```

### 2. Speech (STT) Servisini Başlatma
```bash
python -m modules.voice.speech.xSpeechService --api
```

### 3. Wakeword Servisini Başlatma
```bash
python -m modules.voice.wakeword.xWakewordService --api
```

---

## 💻 Python Kullanım Örnekleri

### 1. Python Kodundan TTS Sentezi (0ms Barge-In ile)
```python
from modules.voice.speak.xSpeakService import SpeakService

service = SpeakService()

# Duygusal tonlama ve prosodi ile konuşma
res = service.speak(
    text="Sistemler aktif. Göreve hazırım!",
    tone="excited", # "happy", "calm", "curious", "neutral"
)
print("Sentezlenen süre:", res["duration_sec"], "saniye")

# Acil durdurma (Barge-In)
service.stop()
```

### 2. AudioRouter Üzerinden Çoklu Dinleyici Kaydetme
```python
from modules.voice.audio_router import get_audio_router, AudioConsumer
import numpy as np

class MySoundListener(AudioConsumer):
    def on_audio_frame(self, frame: np.ndarray, timestamp: float) -> None:
        # 16kHz stereo ses karesi
        pass
    def on_start(self) -> None:
        print("Kayıt başladı")
    def on_stop(self) -> None:
        print("Kayıt bitti")

router = get_audio_router()
router.register_consumer("my_listener", MySoundListener())
router.start()
```

---

## 🌐 HTTP REST API Örnekleri (cURL)

### Robotu Konuşturma (TTS)
```bash
curl -X POST http://127.0.0.1:8083/speak/say \
  -H "Content-Type: application/json" \
  -d '{"text": "SentryBOT devriye moduna geçti.", "tone": "neutral"}'
```

### Konuşmayı Anında Kesme (Barge-In)
```bash
curl -X POST http://127.0.0.1:8083/speak/stop
```

### STT Dinlemeyi Başlatma
```bash
curl -X POST http://127.0.0.1:8084/speech/start
```

### Son Ses Geliş Açısını Alma (DoA)
```bash
curl -X GET http://127.0.0.1:8084/speech/direction
```

---

## 🧪 Testleri Çalıştırma

Ses alt sistemine ait tüm birim ve entegrasyon testlerini çalıştırmak için:

```bash
pytest tests/modules/voice -v
```

---

## 🔗 Detaylı Belgeler
- [architecture_voice.md](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/voice/architecture_voice.md): Sınıf, metot, algoritma ve parametre düzeyinde derin mimari dokümanı.
- [architecture_voice.dot](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/voice/architecture_voice.dot): Graphviz formatında modüler alt sistem çizimi.
- [architecture_voice.svg](file:///c:/Users/emohi/Desktop/Project%20SentryBOT%20V5/modules/voice/architecture_voice.svg): Vektörel mimari şeması.
