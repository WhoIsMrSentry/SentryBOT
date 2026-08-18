# VLM Bridge

SentryBOT'un görsel algı ve köprü modülüdür. Yerel OpenCV pipeline'ı veya uzak VLM sonuç ingest'i ile yüz/kişi/nesne bağlamını üretir; takip, hafıza ve otonomi entegrasyonunu sağlar.

## Sorumluluklar

- Local mode: Haar yüz algılama + ORB/FLANN tanıma + CSRT takip
- Remote mode: dış işlemciden `/vlm/results` ingest
- Yüz takibi, owner follow, head arbiter
- Kişi hafızası, görsel bağlam cache'i, semantic scene
- Autonomy'ye action dispatch (`apply_actions`)
- Vision event bus ve request gate

## Mimari

- Giriş noktası: `xVlmBridgeService.py`
- Ana işlemci: `services/processor.py` (`VisionProcessor`)
- Alt sistemler: `face_manager.py`, `face_emotion.py`, `semantic_describer.py`, `vision_event_bus.py`, `head_control_arbiter.py`, `google_vlm_client.py`
- API parçaları: `api/control.py`, `api/config_routes.py`, `api/analysis.py`, `api/person.py`

Graph'ta `VisionProcessor` gateway bootstrap (`_include_vlm_bridge`) ile başlatılır.

## Mod Yönetimi

- `processing_mode`: `local` | `remote`
- Mod bayrakları: `objects`, `people`, `faces`, `depth`, `ocr`, `hazards`, `semantic_scene`
- Kategori haritası: `local` / `remote` / `onsensor`
- Profiller: `balanced`, `people_focus`, `objects_focus`, `assistive`, `minimal`
- Realtime profiller: `fast`, `normal` (VLM timeout/interval tuning)

## API (Gateway altında `/vlm/*`)

### Kontrol / Takip
- `POST /vlm/track`
- `POST /vlm/follow/start`, `/follow/stop`, `GET /follow/status`
- `POST /vlm/follow/owner/start`
- `POST /vlm/focus/person`
- `GET /vlm/head/status`, `POST /vlm/head/move`

### Mod / Profil
- `GET|POST /vlm/mode`
- `GET|POST /vlm/modes/categories`
- `GET /vlm/profile`, `POST /vlm/profile/switch`

### Sonuç / Bağlam
- `GET /vlm/results/latest`
- `POST /vlm/results`
- `GET /vlm/context/latest`
- `POST /vlm/context/refresh`

### Analiz
- `POST /vlm/analyze`
- `POST /vlm/ask`
- `POST /vlm/ocr`
- `POST /vlm/fer/analyze`
- `GET /vlm/video_feed`

### Yüz / Hafıza
- `POST /vlm/faces/register`, `GET /vlm/faces`
- `POST /vlm/person/remember`, `POST /vlm/person/relationship`
- `GET /vlm/person/{name}`, `GET /vlm/people`
- `POST /vlm/memory/chat`, `GET /vlm/memory/person`, `GET /vlm/memory/people`

### Assistive
- `POST /vlm/blind/start`, `/blind/stop`

## Konfigürasyon

Merkezi kaynak: `config/agent.yaml` → `vlm_bridge`

- `vision.processing_mode`
- `vision_llm` / `google_vlm_client`
- `remote_multimodal`
- `actions.endpoint` (genelde `/autonomy/apply_actions`)
- `vision_request_gate`

## İlişkiler

- `autonomy`: vision hooks, selamlama, world-memory beslemesi
- `camera`: local capture kaynağı
- `arduino_serial`: head/track komutları
- `interactions`, `expression`: görsel olayların ifadeye dönüşümü
- `ollama` / Google VLM: semantic scene üretimi

Otonomlukta proaktif davranışın görsel algı kapısıdır.
