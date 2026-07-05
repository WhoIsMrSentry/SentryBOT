# Skill: arduino_serial

## Ana bileşen
- Sınıf: `SerialTransport` in `modules/arduino_serial/xArduinoSerialService.py`
- Mission: NDJSON seri haberleşme, komut/yanıt kuyruğu

## API özeti
- `GET /healthz` → `healthz()` → get_last_rfid, hello, request, send, telemetry_start
- `POST /send` → `send()` → authorize_rfid, get_last_rfid, laser_on, request, send, telemetry_start
- `POST /request` → `request()` → authorize_rfid, get_last_rfid, laser_on, request, telemetry_start
- `POST /telemetry/start` → `telemetry_start()` → authorize_rfid, cute, get_last_rfid, laser_on, sound_output, telemetry_start
- `POST /telemetry/stop` → `telemetry_stop()` → authorize_rfid, buzzer, cute, get_last_rfid, laser_on, sound_output
- `GET /rfid/last` → `rfid_last()` → authorize_rfid, buzzer, cute, get_last_rfid, laser_on, sound_output, sound_play
- `GET /rfid/authorize` → `rfid_authorize()` → authorize_rfid, buzzer, cute, laser_on, sound_output, sound_play
- `POST /laser/one/{which}` → `laser_one()` → buzzer, cute, laser_on, play_emotion, sound_output, sound_play
- `POST /laser/both` → `laser_both()` → buzzer, cute, play_emotion, sound_output, sound_play
- `POST /laser/off` → `laser_off()` → buzzer, cute, play_emotion, sound_output, sound_play

## Dış ilişkiler (neden)
- → [[config_center]] (import): `arduino_serial` → `config_center`: config/agent.yaml dosyasından ayar okur.

## Gelen ilişkiler (neden)
- ← [[animate]] (arduino): YAML animasyon adımlarını set_pose komutlarına çevirir.
- ← [[animate]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- ← [[animate]] (import): YAML animasyon adımlarını set_pose komutlarına çevirir.
- ← [[animate]] (registry): YAML animasyon adımlarını set_pose komutlarına çevirir.
- ← [[autonomy]] (arduino): Karar sonrası servo/hareket komutlarını donanıma iletir.
- ← [[autonomy]] (import): Karar sonrası servo/hareket komutlarını donanıma iletir.
- ← [[autonomy]] (registry): Karar sonrası servo/hareket komutlarını donanıma iletir.
- ← [[calibration]] (registry): Servo kalibrasyon komutlarını Arduino'ya gönderir.
- ← [[diagnostics]] (http): Arduino bağlantı sağlık testi yapar.
- ← [[diagnostics]] (registry): Arduino bağlantı sağlık testi yapar.

## Tam bilgi
`.sentrybot/obsidian/modules/arduino_serial.md` (19 dosya, 2273 satır)
