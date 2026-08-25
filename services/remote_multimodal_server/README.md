# Remote Multimodal Vision Server

PC-side inference server for SentryBOT, structured similarly to `remote_tts_server`.

## Project Layout

- `app.py` - entrypoint for uvicorn import mode
- `server.py` - compatibility launcher (`python server.py`)
- `remote_multimodal/config.py` - runtime env config
- `remote_multimodal/models.py` - request/response models
- `remote_multimodal/backends.py` - optional backend initialization
- `remote_multimodal/engine.py` - multimodal analysis pipeline
- `remote_multimodal/server.py` - FastAPI routes

## Features

- Face/person detection
- Optional face identity (`face_recognition`)
- Optional age/emotion estimation (`deepface`)
- Object detection (`ultralytics` YOLO if installed, OpenCV fallback otherwise)
- Hybrid vision reasoning: OpenCV/YOLO + Qwen VLM (Ollama)
- Motion score + scene change score
- Hazard hints from object labels
- Optional advanced caption backend (`transformers`)

## Run

```bash
pip install -r requirements.txt
python server.py
```

Default: `http://0.0.0.0:8091`

## Endpoints

- `GET /healthz`
- `POST /vision/analyze` (legacy compatible)
- `POST /vision/analyze/cheap` (objects/people/faces/hazards; never wakes Qwen)
- `POST /vision/analyze/semantic` (explicit semantic VLM budget; may wake Qwen)
- `POST /vision/register_face`
- `POST /vision/ocr` (remote OCR backend)

## Environment Variables

- `MM_HOST` (default `0.0.0.0`)
- `MM_PORT` (default `8091`)
- `MM_AUTH_TOKEN` (default `changeme`)
- `MM_YOLO_MODEL` (default `yolov8n.pt`)
- `MM_FACE_DB` (default `known_faces.json`)
- `MM_DETECTOR_BACKEND` (`auto|yolo|opencv`, default `auto`)
- `MM_RUNTIME_PROFILE` (`ultra_fast|balanced|max_accuracy`, default `balanced`)
- `MM_YOLO_CONF` (default profile-based)
- `MM_YOLO_IMGSZ` (default profile-based)
- `MM_MOTION_THRESHOLD` (default profile-based)
- `MM_SCENE_CHANGE_THRESHOLD` (default profile-based)
- `MM_ENABLE_FACE_RECOGNITION` (`true|false`, default `true`)
- `MM_ENABLE_AGE_EMOTION` (`true|false`, default `true`)
- `MM_ENABLE_QWEN_VLM` (`true|false`, default `true`)
- `MM_QWEN_ENDPOINT` (default `http://whoismrsentry.local:11434/api/chat`)
- `MM_QWEN_PRIMARY_MODEL` (default `qwen3.5:9b`)
- `MM_QWEN_FALLBACK_MODEL` (default `qwen3.5:9b`)
- `MM_QWEN_TIMEOUT` (default `8.0`)
- `MM_QWEN_NUM_PREDICT` (default `192`)
- `MM_QWEN_NUM_CTX` (default `2048`)
- `MM_QWEN_TEMPERATURE` (default `0.1`)
- `MM_ENABLE_ADVANCED_CAPTION` (`true|false`, default `false`)
- `MM_ADVANCED_CAPTION_MODEL` (default `microsoft/Florence-2-base`)

## Recommended Advanced Stack

For your selected profile (`balanced`) with Qwen + OpenCV:

- Detector: YOLO (`ultralytics`)
- Scene reasoning: Qwen VLM via Ollama (`qwen3.5:9b`, fallback `qwen3.5:9b`)
- Face identity: `face_recognition`
- Age/emotion: `deepface`
- Optional caption/reasoning: `transformers` image-to-text backend

## Robot-side config (`modules/vlm_bridge/config/config.yml`)

```yaml
remote_multimodal:
  enabled: true
  endpoint: "http://PC_IP:8091/vision/analyze"
  ocr_endpoint: "http://PC_IP:8091/vision/ocr"
  timeout_s: 6.0
  ocr_timeout_s: 10.0
  auth_token: "YOUR_TOKEN"
  ocr_languages: ["en", "tr"]
```
