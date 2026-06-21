# Sub-Agent: speech-specialist

## Uzmanlık
`SpeechService` ve `speech` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/speech.md`

## Bileşen haritası
- `AudioCapture` — Singleton audio capture supporting multiple broadcast subscribers.
- `AudioConfig` — modules/speech/services/audio_capture.py
- `ArrayGeometry` — modules/speech/services/direction.py
- `DirectionEstimator` — Estimate direction of arrival (azimuth) using two mics via GCC-PHAT.
- `PanTiltConfig` — modules/speech/services/pan_tilt.py
- `PanTiltController` — Minimal pan controller with slew limiting and callback sender.
- `RecognitionResult` — modules/speech/services/recognizer.py
- `Recognizer` — modules/speech/services/recognizer.py
- `RecognizerConfig` — modules/speech/services/recognizer.py
- `SpeechService` — High-level facade to run audio capture and speech recognition.

## Dış bağlantılar (neden)
- [[agent_core]] (http): `speech` HTTP ile `agent_core` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[arduino_serial]] (arduino): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- [[arduino_serial]] (http): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- [[arduino_serial]] (import): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- [[config_center]] (import): `speech` → `config_center`: config/agent.yaml dosyasından ayar okur.
- [[gateway]] (import): `speech` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- [[interactions]] (http): `speech` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- [[logwrapper]] (import): `speech` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- [[speak]] (http): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.
- [[speak]] (import): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.

## Gelen bağlantılar (neden)
- [[agent_core]] (http): `agent_core` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[agent_core]] (http): `agent_core` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[autonomy]] (http): `autonomy` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[autonomy]] (http): `autonomy` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[autonomy]] (import): `autonomy` kod içinde `speech` modülünü import eder (`services`) — Çok kanallı ASR, Vosk/Whisper, ses yönü (DOA).
- [[diagnostics]] (http): `diagnostics` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- [[gateway]] (import): `gateway` kod içinde `speech` modülünü import eder (`xSpeechService`) — Çok kanallı ASR, Vosk/Whisper, ses yönü (DOA).
