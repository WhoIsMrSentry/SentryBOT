# Sub-Agent: vlm_bridge-specialist

## Uzmanlık
`VisionProcessor` ve `vlm_bridge` modül ekosistemi.

## Bilgi kaynağı
`.sentrybot/obsidian/modules/vlm_bridge.md`

## Bileşen haritası
- `VisionActionDispatcher` — Parses semantic descriptions and forwards action tags to Autonomy.
- `FaceManager` — OpenCV ORB + FLANN tabanli hafif yuz tanima yoneticisi.
- `GoogleVLMClient` — Gemini multimodal client with the same surface as :class:`OllamaVLMClient`.
- `HeadCommand` — modules/vlm_bridge/services/head_control_arbiter.py
- `HeadControlArbiter` — Thread-safe head movement arbiter with priority and clamping.
- `OllamaVLMClient` — HTTP client for remote Ollama VLM inference.
- `PeopleMemory` — Per-person chat history and last-summary memory.
- `PersonIdentityManager` — Manages person recognition, relationship levels, and persistence.
- `PersonMemoryRecord` — modules/vlm_bridge/services/person_identity.py
- `VisionProcessor` — YOLO'suz VLM Bridge isleyici.
- `SemanticDescriber` — modules/vlm_bridge/services/semantic_describer.py
- `xArduinoSerialService` — modules/vlm_bridge/services/stub.py

## Dış bağlantılar (neden)
- [[arduino_serial]] (arduino): Pan/tilt servo takibi için Arduino komutları gönderir.
- [[arduino_serial]] (http): Pan/tilt servo takibi için Arduino komutları gönderir.
- [[arduino_serial]] (import): Pan/tilt servo takibi için Arduino komutları gönderir.
- [[arduino_serial]] (registry): Pan/tilt servo takibi için Arduino komutları gönderir.
- [[camera]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- [[camera]] (http): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- [[camera]] (import): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- [[camera]] (registry): MJPEG/frame kaynağı olarak kamera stream'ini kullanır.
- [[config_center]] (import): `vlm_bridge` → `config_center`: config/agent.yaml dosyasından ayar okur.
- [[config_center]] (import): `vlm_bridge` içinde `gemini_model` import edilir; `config_center` modülünün yeteneğini kullanır (Merkezi config okuma/yazma, hot-reload).
- [[gateway]] (import): `vlm_bridge` içinde `url` import edilir; `gateway` modülünün yeteneğini kullanır (FastAPI API bootstrapper, tüm modülleri mount eder).
- [[interactions]] (http): `vlm_bridge` HTTP ile `interactions` modülüne erişir: Sistem olayı veya LED efekti tetikler.

## Gelen bağlantılar (neden)
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (http): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[agent_core]] (import): Görsel araçlar ve vision context için VLM köprüsüne bağlanır.
- [[autonomy]] (registry): Görsel bağlam ve yüz tanıma verisi alır.
- [[common]] (http): `common` `vlm_bridge` modülünün HTTP API'sine istek atar (calls path `/vlm/context/latest`).
- [[common]] (http): `common` `vlm_bridge` modülünün HTTP API'sine istek atar (calls path `/vlm/results/latest`).
- [[gateway]] (http): `gateway` `vlm_bridge` modülünün HTTP API'sine istek atar (calls path `/vlm`).
- [[gateway]] (import): `gateway` kod içinde `vlm_bridge` modülünü import eder (`config_loader`) — OpenCV yüz algılama, ORB/FLANN eşleme, CSRT takip, remote VLM.
