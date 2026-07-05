# Sub-Agent: speak-specialist

## Uzmanlık
`SpeakService` ve `speak` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/speak.md`

## Bileşen haritası
- `PCM` — Basit PCM veri taşıyıcısı.
- `AudioPlayer` — modules/speak/services/player.py
- `OutputConfig` — modules/speak/services/player.py
- `DummyBackend` — modules/speak/services/tts.py
- `PiperBackend` — Piper TTS with lazy-loaded per-voice models (language_voices / voices map).
- `Pyttsx3Backend` — modules/speak/services/tts.py
- `RemoteTTSHttpBackend` — Unified remote TTS backend for piper/xtts with a single endpoint.
- `TTSBackend` — modules/speak/services/tts.py
- `TTSConfig` — modules/speak/services/tts.py
- `TextToSpeech` — modules/speak/services/tts.py
- `XTTSHttpBackend` — XTTS via external local HTTP service.
- `_PiperModel` — Single Piper ONNX voice runner.

## Dış bağlantılar (neden)
- [[common]] (import): Duygu tonu ve emotion_vocab ile TTS tonunu eşler.
- [[config_center]] (import): config/agent.yaml içindeki speak ayarlarını okur.
- [[logwrapper]] (import): `speak` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- [[neopixel]] (registry): Konuşma sırasında LED canlılık efektleri (liveliness) tetikler.

## Gelen bağlantılar (neden)
- [[autonomy]] (import): Sense-Think-Act döngüsü LLM yanıtını seslendirmek için TTS çağırır.
- [[autonomy]] (registry): Sense-Think-Act döngüsü LLM yanıtını seslendirmek için TTS çağırır.
- [[diagnostics]] (http): `diagnostics` → `speak`: TTS servisinin hazır olup olmadığını kontrol eder.
- [[gateway]] (http): `gateway` → `speak`: TTS servisinin hazır olup olmadığını kontrol eder.
- [[gateway]] (http): `gateway` → `speak`: Devam eden konuşmayı keser.
- [[gateway]] (http): `gateway` `speak` modülünün HTTP API'sine istek atar (calls path `/speak`).
- [[gateway]] (import): `gateway` kod içinde `speak` modülünü import eder (`xSpeakService`) — TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı.
- [[gateway]] (import): `gateway` kod içinde `speak` modülünü import eder (`api`) — TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı.
- [[scheduler]] (http): Zamanlanmış görevlerde hatırlatma/duyuru metni seslendirir.
- [[speech]] (http): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.
- [[speech]] (import): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.
