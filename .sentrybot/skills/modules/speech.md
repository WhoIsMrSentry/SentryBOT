# Skill: speech

## Ana bileşen
- Sınıf: `SpeechService` in `modules/speech/xSpeechService.py`
- Mission: Çok kanallı ASR, Vosk/Whisper, ses yönü (DOA)

## API özeti
- `GET /speech/status` → `status()` → is_stt_suppressed
- `POST /speech/start` → `start()` → clear_utterance_buffer, start_background, stop, track_start
- `POST /speech/stop` → `stop()` → stop, track_start, track_status, track_stop
- `GET /speech/last` → `last_result()` → set_stt_suppressed, track_start, track_status, track_stop
- `GET /speech/direction` → `direction()` → set_stt_suppressed, track_start, track_status, track_stop
- `POST /speech/track/start` → `track_start()` → set_stt_suppressed, track_start, track_status, track_stop
- `POST /speech/track/stop` → `track_stop()` → set_stt_suppressed, track_status, track_stop
- `GET /speech/track/status` → `track_status()` → set_stt_suppressed, track_status
- `POST /speech/stt/suppress` → `stt_suppress()` → set_stt_suppressed

## Dış ilişkiler (neden)
- → [[agent_core]] (http): `speech` HTTP ile `agent_core` modülüne erişir: Ses tanıma (ASR) pipeline'ına istek gönderir.
- → [[arduino_serial]] (arduino): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- → [[arduino_serial]] (http): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- → [[arduino_serial]] (import): Ses yönü (DOA) veya buzzer geri bildirimi için Arduino'ya komut gönderir.
- → [[config_center]] (import): `speech` → `config_center`: config/agent.yaml dosyasından ayar okur.
- → [[gateway]] (import): `speech` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- → [[interactions]] (http): `speech` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.
- → [[logwrapper]] (import): `speech` → `logwrapper`: Merkezi WebSocket log yayınına bağlanır.
- → [[speak]] (http): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.
- → [[speak]] (import): ASR sonrası geri bildirim veya onay cümlelerini TTS ile okutabilir.

## Gelen ilişkiler (neden)
- ← [[agent_core]] (http): `agent_core` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[agent_core]] (http): `agent_core` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[autonomy]] (http): `autonomy` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[autonomy]] (http): `autonomy` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[autonomy]] (import): `autonomy` kod içinde `speech` modülünü import eder (`services`) — Çok kanallı ASR, Vosk/Whisper, ses yönü (DOA).
- ← [[diagnostics]] (http): `diagnostics` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.
- ← [[gateway]] (http): `gateway` → `speech`: Ses tanıma (ASR) pipeline'ına istek gönderir.

## Tam bilgi
`.sentrybot/obsidian/modules/speech.md` (21 dosya, 1746 satır)
