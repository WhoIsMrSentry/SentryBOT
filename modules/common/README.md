# Common

Modüller arasında paylaşılan, hafif yardımcı kütüphaneler modülüdür. Ağır modül grafiklerini import etmeden ortak davranış sağlar.

## Sorumluluklar

- **Kanonik Duygu Sözlüğü** (`emotion_vocab.py`) - **MERKEZİ KAYNAK**
- Latency trace deposu (`latency_trace.py`)
- HTTP istemci yardımcıları (`http_client.py`)
- Vision/camera kullanılabilirlik kontrolleri (`vision_availability.py`)
- Model asset doğruluk raporu (`model_asset_truth.py`)
- Runtime hedef tespiti (`runtime_target.py`)
- Sistem prompt yardımcıları (`system_prompts.py`)

## Duygu Sözlüğü (KRİTİK - Tek Kaynak)

`emotion_vocab.py`, **TÜM** ifade/modalite modülleri arasında tek duygu taksonomisi sağlar:

| Modül (Yeni Yol) | Kullanım |
|------------------|----------|
| `visual_output/neopixel` | Palette/effect eşlemesi, companion modes |
| `visual_output/oled_faces` | Mood/activity/gesture render hints |
| `expression/piservo` | Emotion → kulak pozisyonu |
| `expression/animate` | Animasyon sekansında emotion trigger |
| `voice/speak` | Tone/prosody preset mapping |
| `autonomy` | MoodManager, NeedsEngine, companion state |
| `agent_core` | Tool descriptions, expression tool |
| `expression` | SemanticExpressionEngine, ExpressionArbiter |

```python
from modules.common.emotion_vocab import get_vocab

vocab = get_vocab()
vocab.canonical("happy")   # -> "joy" (alias resolution)
vocab.canonical("mutlu")   # -> "joy" (TR alias)
render = vocab.render("joy")
# render.oled (mood name), render.palette (neo variant), render.tone (speak preset), render.rgb (fallback)
```

**Config:** `modules/common/config/emotions.yml` - Tek kaynak, tüm modüller bunu import eder.

## Diğer Yardımcılar

| Dosya | Açıklama | Kullananlar |
|-------|----------|-------------|
| `latency_trace.py` | Uçtan uca gecikme izleri (trace_id, spans) | `voice/speak`, `agent_core`, `vlm_bridge` |
| `http_client.py` | Async/sync HTTP wrapper (retry, timeout) | `ai_provider`, `vlm_bridge/google_vlm_client`, `autonomy/client` |
| `vision_availability.py` | Kamera/VLM girdisinin gerçekten kullanılabilir olup olmadığını kontrol | `agent_core/tools`, `vlm_bridge`, `autonomy/vision_context` |
| `runtime_target.py` | Pi/PC hedef ortamını tespit etme (`assert_raspberry_pi()`) | `sentrybot.py` preflight, `camera`, `hardware` tests |
| `model_asset_truth.py` | Model dosyası varlık doğrulaması (piper, openwakeword) | `voice/speech`, `voice/speak`, `voice/wakeword` |
| `lang_names.py` | Dil kodu → insan okunur dil adı eşlemesi (TTS/STT dili raporlaması için) | `agent_core` |

## İlişkiler

`common` bir servis değil, **paylaşılan kütüphane katmanıdır**. Özellikle:
- **Otonom ifade senkronizasyonu** → `emotion_vocab` (tek kaynak)
- **Performans gözlemi** → `latency_trace`
- **Model doğruluk** → `model_asset_truth`

**Kural:** Hiçbir modül kendi emotion map/render/palette tutmamalı. Hepsi `from modules.common.emotion_vocab import get_vocab` kullanmalı.

## Durum (Güncel 2026-08-21, Tam Tarama)

| İhtiyaç | Durum | Dosya |
|---------|-------|-------|
| Config Loader Base | ✅ FIXED | `common/config_loader.py:599` tek kaynak, `deep_merge`+`require_dict_section` ortak |
| Service Base | ✅ EKLENDİ | `common/service_base.py` + `BackgroundTaskMixin` |
| Event Bus | ✅ EKLENDİ | `common/event_bus.py` `EventBus` async, `get_event_bus`, `publish_sync` |
| Health Standard | ✅ EKLENDİ | `common/health.py` `HealthResponse`+`HealthChecker` |
| Router Factory | ✅ EKLENDİ | `common/router_factory.py:create_router` |
| Gateway URL | ✅ FIXED | `common/config_loader.py:gateway_base_from_agent_cfg` re-export, `gateway/url.py` hala var ama `common` tek kaynak |
| Persistence | ✅ EKLENDİ | `common/persistence.py` SQLite/WAL+JSON+Memory |
| Job Types | ✅ EKLENDİ | `common/job_types.py` `JobRegistry` plugin |
| Command Registry | ✅ EKLENDİ | `common/command_registry.py` |
| Model Policy | ✅ EKLENDİ | `common/model_policy.py:get_model_policy` |
| Device Manager | ❌ EKSİK | `camera/device_manager.py` YENİ eklendi ama `common` değil, `voice/audio_router.py` YENİ eklendi |

Kalan: `common` artık `core layer 55 in` en yüksek fan-in, `router_factory` henüz 0 adopt.