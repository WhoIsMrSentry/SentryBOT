# Skill: vlm_bridge

## Ana bileşen
- Sınıf: `VisionProcessor` in `modules/vlm_bridge/xVlmBridgeService.py`
- Mission: OpenCV yüz algılama, ORB/FLANN eşleme, CSRT takip, remote VLM

## API özeti
- `POST /track` → `track()` → —
- `POST /follow/start` → `follow_start()` → —
- `POST /follow/stop` → `follow_stop()` → —
- `GET /follow/status` → `follow_status()` → —
- `GET /mode` → `get_mode()` → —
- `GET /profile` → `get_profile()` → —
- `POST /profile/switch` → `switch_profile()` → —
- `GET /modes/categories` → `get_mode_categories()` → —
- `POST /modes/categories` → `patch_mode_categories()` → —
- `POST /mode` → `set_mode()` → —

## Dış ilişkiler (neden)
- → [[arduino_serial]] (arduino): Pan/tilt servo takibi için Arduino komutları gönderir.
- → [[arduino_serial]] (http): Pan/tilt servo takibi için Arduino komutları gönderir.
- → [[arduino_serial]] (import): Pan/tilt servo takibi için Arduino komutları gönderir.
- → [[arduino_serial]] (registry): Pan/tilt servo takibi için Arduino komutları gönderir.
- → [[camera]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- → [[camera]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- → [[camera]] (import): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- → [[camera]] (registry): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- → [[config_center]] (import): `vlm_bridge` → `config_center`: config/agent.yaml dosyasından ayar okur.
- → [[config_center]] (import): `vlm_bridge` içinde `gemini_model` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).

## Gelen ilişkiler (neden)
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[agent_core]] (import): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- ← [[autonomy]] (registry): Görsel bağlam ve yüz tanıma verisi alır.
- ← [[common]] (http): `common` `vlm_bridge` modülünün HTTP API'sine istek atar (calls path `/vlm/context/latest`).
- ← [[common]] (http): `common` `vlm_bridge` modülünün HTTP API'sine istek atar (calls path `/vlm/results/latest`).

## Tam bilgi
`.sentrybot/obsidian/modules/vlm_bridge.md` (36 dosya, 6372 satır)
