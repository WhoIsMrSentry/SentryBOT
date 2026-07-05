# Skill: speak

## Ana bileşen
- Sınıf: `SpeakService` in `modules/speak/xSpeakService.py`
- Mission: TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı

## API özeti
- `GET /speak/status` → `status()` → speak, stop_speaking
- `POST /speak/stop` → `stop()` → speak, stop_speaking
- `POST /speak/say` → `say()` → speak
- `POST /speak/say_stream` → `say_stream()` → speak
- `GET /speak/jobs/{job_id}` → `job_status()` → play_wav
- `POST /speak/play` → `play()` → play_wav

## Dış ilişkiler (neden)
- → [[common]] (import): Duygu tonu ve emotion_vocab ile TTS tonunu eşler.
- → [[config_center]] (import): config/agent.yaml içindeki speak ayarlarını okur.
- → [[logwrapper]] (import): `speak` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- → [[neopixel]] (registry): Konuşma sırasında LED canlılık efektleri (liveliness) tetikler.

## Gelen ilişkiler (neden)
- ← [[autonomy]] (import): Sense-Think-Act döngüsü LLM yanıtını seslendirmek için TTS çağırır.
- ← [[autonomy]] (registry): Sense-Think-Act döngüsü LLM yanıtını seslendirmek için TTS çağırır.
- ← [[diagnostics]] (http): `diagnostics` → `speak`: TTS servisinin hazır olup olmadığını kontrol eder.
- ← [[gateway]] (http): `gateway` → `speak`: TTS servisinin hazır olup olmadığını kontrol eder.
- ← [[gateway]] (http): `gateway` → `speak`: Devam eden konuşmayı keser.
- ← [[gateway]] (http): `gateway` `speak` modülünün HTTP API'sine istek atar (calls path `/speak`).
- ← [[gateway]] (import): `gateway` kod içinde `speak` modülünü import eder (`xSpeakService`) — TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı.
- ← [[gateway]] (import): `gateway` kod içinde `speak` modülünü import eder (`api`) — TTS sentez (pyttsx3/Piper/xTTS), ton/duygu ayarı.
- ← [[scheduler]] (http): Zamanlanmış görevlerde hatırlatma/duyuru metni seslendirir.
- ← [[speech]] (http): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.

## Tam bilgi
`.sentrybot/obsidian/modules/speak.md` (26 dosya, 2453 satır)
